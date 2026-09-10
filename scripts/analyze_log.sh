#!/usr/bin/env bash
#
# analyze_log.sh —— Nginx 访问日志分析工具
#
# 把 study/7.2 里练的文本三剑客(grep/awk/sort|uniq)沉淀成可复用脚本。
# 依赖 frontend/nginx.conf 的自定义 log_format `timed`(末尾带 rt=请求耗时)。
# 兼容标准 combined 格式:没有 rt= 字段时自动跳过慢请求分析,不报错。
#
# 用法:
#   ./scripts/analyze_log.sh [日志文件] [慢请求阈值秒]
#   ./scripts/analyze_log.sh /var/log/nginx/access.log 0.9
#   docker compose exec frontend sh -c 'cat /var/log/nginx/access.log' | ./scripts/analyze_log.sh -
#   TOP_N=20 ./scripts/analyze_log.sh access.log
#
# 参数:
#   $1  日志文件路径,或 - 表示从 stdin 读(默认 /var/log/nginx/access.log)
#   $2  慢请求阈值(秒),默认 0.9(呼应 study 里的 $11>0.9)
# 环境变量:
#   TOP_N  各排行榜取前几名(默认 10)

set -Eeuo pipefail

readonly LOG_FILE="${1:-/var/log/nginx/access.log}"
readonly SLOW_THRESHOLD="${2:-0.9}"
readonly TOP_N="${TOP_N:-10}"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }
fail() { printf '[%s] ERROR: %s\n' "$(date '+%F %T')" "$*" >&2; exit 1; }

# ── 读入日志到临时文件(统一处理文件/stdin,便于多次扫描) ──────────────
readonly TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if [[ "$LOG_FILE" == "-" ]]; then
    cat > "$TMP"
elif [[ -f "$LOG_FILE" ]]; then
    cat "$LOG_FILE" > "$TMP"
else
    fail "日志文件不存在:${LOG_FILE}(用 - 从 stdin 读)"
fi

readonly TOTAL="$(grep -c . "$TMP" || true)"
[[ "$TOTAL" -gt 0 ]] || fail "日志为空,无可分析内容"

hr() { printf '%s\n' "------------------------------------------------------------"; }
section() { hr; printf '  %s\n' "$*"; hr; }

# ── 总览 ────────────────────────────────────────────────────────────
section "总览"
printf '  日志文件      : %s\n' "$LOG_FILE"
printf '  总请求数      : %s\n' "$TOTAL"
# 时间跨度:combined 格式第 4 段是 [dd/Mon/yyyy:HH:MM:SS,去掉前导 [
first_ts="$(awk 'NR==1{print substr($4,2)}' "$TMP")"
last_ts="$(awk 'END{print substr($4,2)}' "$TMP")"
printf '  时间跨度      : %s ~ %s\n' "${first_ts:-?}" "${last_ts:-?}"

# ── 状态码分布 ──────────────────────────────────────────────────────
# combined 格式:$9 是状态码。按次数降序,并标注 2xx/3xx/4xx/5xx 大类占比。
section "状态码分布"
awk '{c[$9]++} END{for(s in c) printf "  %-6s %8d  (%.1f%%)\n", s, c[s], c[s]*100/NR}' "$TMP" \
    | sort -k2 -rn
printf '  ---\n'
awk '{k=substr($9,1,1)"xx"; g[k]++}
     END{for(x in g) printf "  %-6s %8d  (%.1f%%)\n", x, g[x], g[x]*100/NR}' "$TMP" \
    | sort

# ── Top URL(按访问量) ──────────────────────────────────────────────
# $6 是 "METHOD,$7 是 URL,$8 是协议"。这里取 method+url。
section "Top ${TOP_N} URL(按访问量)"
awk '{print $6" "$7}' "$TMP" | sed 's/"//g' \
    | sort | uniq -c | sort -rn | head -n "$TOP_N" \
    | awk '{printf "  %8d  %s %s\n", $1, $2, $3}'

# ── Top 客户端 IP ──────────────────────────────────────────────────
section "Top ${TOP_N} 客户端 IP"
awk '{print $1}' "$TMP" | sort | uniq -c | sort -rn | head -n "$TOP_N" \
    | awk '{printf "  %8d  %s\n", $1, $2}'

# ── 错误请求(4xx / 5xx)摘要 ───────────────────────────────────────
section "错误请求(4xx / 5xx)Top ${TOP_N}"
err_count="$(awk '$9 ~ /^[45]/' "$TMP" | wc -l)"
if [[ "$err_count" -gt 0 ]]; then
    printf '  错误总数:%s(%.1f%%)\n\n' "$err_count" \
        "$(awk -v e="$err_count" -v t="$TOTAL" 'BEGIN{printf e*100/t}')"
    awk '$9 ~ /^[45]/ {print $9" "$6" "$7}' "$TMP" | sed 's/"//g' \
        | sort | uniq -c | sort -rn | head -n "$TOP_N" \
        | awk '{printf "  %8d  [%s] %s %s\n", $1, $2, $3, $4}'
else
    printf '  无 4xx/5xx 错误 ✓\n'
fi

# ── 慢请求分析(依赖 rt= 字段) ─────────────────────────────────────
# study 里练的核心:按请求耗时筛慢请求。log_format `timed` 末尾是 rt=<秒>。
section "慢请求(rt > ${SLOW_THRESHOLD}s)Top ${TOP_N}"
if grep -q 'rt=' "$TMP"; then
    # 从每行抽出 rt= 后的数字(用 gsub 提取,不依赖列位置),配合 method+url 输出
    awk -v th="$SLOW_THRESHOLD" '
        {
            rt = ""
            for (i = 1; i <= NF; i++) if ($i ~ /^rt=/) { rt = substr($i, 4); break }
            if (rt != "" && rt + 0 > th + 0) {
                url = $6" "$7; gsub(/"/, "", url)
                printf "%.3f %s\n", rt, url
            }
        }' "$TMP" | sort -rn | head -n "$TOP_N" \
        | awk '{printf "  %8.3fs  %s %s\n", $1, $2, $3}'

    # 顺带给出耗时分位(P50/P95/P99),定位整体性能而非单点
    printf '  ---\n'
    awk '{ for (i=1;i<=NF;i++) if ($i ~ /^rt=/) print substr($i,4) }' "$TMP" \
        | sort -n \
        | awk '{a[NR]=$1} END{
            if (NR==0) { print "  (无 rt 样本)"; exit }
            p50=a[int(NR*0.50)]; p95=a[int(NR*0.95)]; p99=a[int(NR*0.99)]
            printf "  耗时分位  P50=%.3fs  P95=%.3fs  P99=%.3fs  (样本 %d)\n", p50, p95, p99, NR
        }'
else
    printf '  日志无 rt= 字段(非 timed 格式),跳过慢请求分析。\n'
    printf '  提示:frontend/nginx.conf 已配置 timed 格式,重建 frontend 容器后生效。\n'
fi

hr
log "分析完成"
