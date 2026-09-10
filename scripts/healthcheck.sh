#!/usr/bin/env bash
#
# healthcheck.sh —— WhaleTestPro 全栈健康巡检
#
# 一键体检 docker compose 起的全部服务:容器状态、后端 HTTP、
# MySQL / Redis / RabbitMQ 存活、磁盘水位。适合部署后验收或定时巡检(cron)。
#
# 用法:
#   ./scripts/healthcheck.sh              # 巡检所有项
#   ./scripts/healthcheck.sh --quiet      # 只在有异常时输出(适合 cron)
#   HEALTH_URL=http://127.0.0.1:8001/health ./scripts/healthcheck.sh
#
# 退出码:0=全部健康;非 0=有 N 项异常(N 即退出码,便于外层判断/告警)

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8001/health}"
readonly DISK_THRESHOLD="${DISK_THRESHOLD:-85}"   # 磁盘使用率告警阈值(%)
QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

# ── 计数与输出 ──────────────────────────────────────────────────────
FAIL_COUNT=0
BUFFER=""

emit() { BUFFER+="$*"$'\n'; }
ok()   { emit "  [ OK ]  $*"; }
warn() { emit "  [WARN]  $*"; }
bad()  { emit "  [FAIL]  $*"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
section() { emit ""; emit "── $* ─────────────────────────────"; }

# compose 命令探测(新旧两种写法)
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    DC=""
fi

cd "$PROJECT_DIR"

# ── 1. 容器状态 ─────────────────────────────────────────────────────
section "容器状态"
if [[ -z "$DC" ]]; then
    bad "未找到 docker compose,跳过容器检查"
else
    # 期望常驻的核心服务
    for svc in mysql redis rabbitmq app worker frontend; do
        cid="$($DC ps -q "$svc" 2>/dev/null || true)"
        if [[ -z "$cid" ]]; then
            bad "服务 ${svc}:未创建/未运行"
            continue
        fi
        state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
        # 有 healthcheck 的容器额外读健康态
        health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$cid" 2>/dev/null || echo -)"
        if [[ "$state" == "running" && ( "$health" == "healthy" || "$health" == "-" ) ]]; then
            ok "服务 ${svc}:running${health:+ / $health}"
        elif [[ "$state" == "running" && "$health" == "starting" ]]; then
            warn "服务 ${svc}:running / starting(健康检查预热中)"
        else
            bad "服务 ${svc}:${state} / ${health}"
        fi
    done
fi

# ── 2. 后端 HTTP /health ───────────────────────────────────────────
section "后端 HTTP"
if command -v curl >/dev/null 2>&1; then
    code="$(curl -o /dev/null -s -w '%{http_code}' --max-time 5 "$HEALTH_URL" 2>/dev/null || echo 000)"
    if [[ "$code" == "200" ]]; then
        ok "GET ${HEALTH_URL} -> 200"
    else
        bad "GET ${HEALTH_URL} -> ${code}(期望 200)"
    fi
else
    warn "无 curl,跳过 HTTP 检查"
fi

# ── 3. 中间件存活(容器内 ping) ────────────────────────────────────
section "中间件"
if [[ -n "$DC" ]]; then
    # MySQL
    if $DC exec -T mysql sh -c 'mysqladmin ping -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD"' 2>/dev/null | grep -q 'alive'; then
        ok "MySQL:mysqld is alive"
    else
        bad "MySQL:ping 失败"
    fi
    # Redis
    if [[ "$($DC exec -T redis redis-cli ping 2>/dev/null | tr -d '\r')" == "PONG" ]]; then
        ok "Redis:PONG"
    else
        bad "Redis:ping 失败"
    fi
    # RabbitMQ
    if $DC exec -T rabbitmq rabbitmq-diagnostics -q ping >/dev/null 2>&1; then
        ok "RabbitMQ:ping ok"
    else
        bad "RabbitMQ:ping 失败"
    fi
else
    warn "无 docker compose,跳过中间件检查"
fi

# ── 4. 磁盘水位 ─────────────────────────────────────────────────────
section "磁盘"
usage="$(df -P "$PROJECT_DIR" | awk 'NR==2{gsub(/%/,"",$5); print $5}')"
if [[ -n "$usage" ]]; then
    if (( usage < DISK_THRESHOLD )); then
        ok "项目所在分区使用率:${usage}%(阈值 ${DISK_THRESHOLD}%)"
    else
        bad "项目所在分区使用率:${usage}% ≥ 阈值 ${DISK_THRESHOLD}%"
    fi
else
    warn "无法读取磁盘使用率"
fi

# ── 汇总 ────────────────────────────────────────────────────────────
emit ""
if (( FAIL_COUNT == 0 )); then
    emit "══ 巡检结果:全部健康 ✓ ══"
else
    emit "══ 巡检结果:${FAIL_COUNT} 项异常 ✗ ══"
fi

# --quiet 且全绿时静默(cron 友好);否则输出全部
if (( QUIET == 1 && FAIL_COUNT == 0 )); then
    :
else
    printf '%s' "$BUFFER"
fi

exit "$FAIL_COUNT"
