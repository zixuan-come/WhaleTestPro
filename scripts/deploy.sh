#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly BRANCH="${DEPLOY_BRANCH:-main}"
readonly HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/api/health}"
readonly MAX_ATTEMPTS="${HEALTH_MAX_ATTEMPTS:-30}"
readonly WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-2}"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
    log "ERROR: $*" >&2
    exit 1
}

on_error() {
    local exit_code=$?
    local line=$1
    local command=$2
    log "部署失败：第 ${line} 行，命令：${command}" >&2
    exit "$exit_code"
}

trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

for command in git docker curl flock; do
    command -v "$command" >/dev/null 2>&1 \
        || fail "缺少命令：${command}"
done

exec 9>/tmp/whaletestpro-deploy.lock
flock -n 9 || fail "已有部署任务正在运行"

cd "$PROJECT_DIR"

[[ -f .env ]] || fail "项目根目录缺少 .env"

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "$BRANCH" ]] \
    || fail "当前分支是 ${current_branch}，预期是 ${BRANCH}"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
    git status --short
    fail "服务器仓库存在本地修改，拒绝覆盖"
fi

old_commit="$(git rev-parse --short HEAD)"
log "当前版本：${old_commit}"



log "同步 GitHub"
git fetch origin "$BRANCH"

remote_ref="origin/${BRANCH}"

if ! git merge-base --is-ancestor HEAD "$remote_ref"; then
    fail "服务器包含远端不存在的提交，拒绝部署"
fi

git merge --ff-only "$remote_ref"



new_commit="$(git rev-parse --short HEAD)"
log "目标版本：${new_commit}"

log "校验 Compose"
sudo docker compose config --quiet

log "构建并更新容器"
sudo docker compose up -d --build --remove-orphans

log "等待健康检查：${HEALTH_URL}"
attempt=1
healthy=0

while (( attempt <= MAX_ATTEMPTS )); do
    if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
        healthy=1
        break
    fi

    log "健康检查未通过（${attempt}/${MAX_ATTEMPTS}）"
    sleep "$WAIT_SECONDS"
    attempt=$((attempt + 1))
done

if (( healthy == 0 )); then
    sudo docker compose logs --tail=80 app frontend || true
    fail "健康检查超时"
fi

exited="$(sudo docker compose ps --status exited --quiet)"
restarting="$(sudo docker compose ps --status restarting --quiet)"

if [[ -n "${exited}${restarting}" ]]; then
    sudo docker compose ps -a
    fail "存在退出或持续重启的容器"
fi

sudo docker compose ps
log "部署成功：${old_commit} -> ${new_commit}"
