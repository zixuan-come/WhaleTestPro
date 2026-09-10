# scripts/ —— 运维脚本

WhaleTestPro 的运维/自动化脚本。全部遵循同一工程规格：`set -Eeuo pipefail`、结构化 `log()` 输出、明确退出码。

| 脚本 | 用途 | 关联 |
|---|---|---|
| `deploy.sh` | 生产部署：拉代码 → compose 构建 → 健康检查 → 失败回滚提示 | 部署流程 |
| `analyze_log.sh` | Nginx 访问日志分析 | 架构线 D #21（文本三剑客沉淀） |
| `healthcheck.sh` | 全栈健康巡检 | 架构线 D #21 / 运维 |

## analyze_log.sh —— 访问日志分析

把 study/7.2 里练的 grep/awk/sort\|uniq 技能沉淀成可复用工具。输出：总览、状态码分布（含 2xx/4xx/5xx 大类）、Top URL、Top IP、错误摘要、慢请求（按 `rt=` 耗时筛）+ P50/P95/P99 分位。

依赖 `frontend/nginx.conf` 的自定义 `log_format timed`（末尾带 `rt=$request_time`）；遇到无 `rt=` 的标准 combined 日志会自动跳过慢请求分析、不报错。

```bash
./scripts/analyze_log.sh /var/log/nginx/access.log 0.9    # 文件 + 慢请求阈值(秒)
docker compose exec frontend cat /var/log/nginx/access.log | ./scripts/analyze_log.sh - 0.9
TOP_N=20 ./scripts/analyze_log.sh access.log              # 排行榜取前 20
```

## healthcheck.sh —— 全栈健康巡检

一键体检 compose 起的全部服务：容器状态（含 healthcheck 健康态）、后端 `/health` HTTP、MySQL/Redis/RabbitMQ 存活 ping、磁盘水位。**退出码 = 异常项数**（0=全健康），适合 cron 定时巡检 + 告警。

```bash
./scripts/healthcheck.sh                    # 完整报告
./scripts/healthcheck.sh --quiet            # 只在有异常时输出(cron 友好)
HEALTH_URL=http://127.0.0.1:8001/health DISK_THRESHOLD=90 ./scripts/healthcheck.sh

# cron 示例：每 5 分钟巡检，异常才发邮件
# */5 * * * * /path/to/scripts/healthcheck.sh --quiet || mail -s 'WhaleTestPro 异常' you@x.com
```
