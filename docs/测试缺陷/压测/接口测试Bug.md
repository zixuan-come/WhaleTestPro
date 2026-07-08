# 压测 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-038 | P2 | spec 模块12 路由写 `/perf`,实际代码/前端均为 `/perf/tasks` | spec 接口清单写 `POST /perf` 等;但 `perf.py` router `prefix="/perf/tasks"`,前端 `api/perf.js` 也用 `/perf/tasks`。代码与前端一致、唯 spec 文档写错 | spec 文档笔误,路由前缀漏 `/tasks` 段 | 用例设计新发现 | 待修(改文档) |
| BUG-039 | P1 | 压测字段无长度/范围校验、空必填可建、超长/负数 → 500 或运行期异常 | schema `PerfTaskCreate` `name/target_host/target_path: str` 无 `min/max_length`:空经 API → 201;name>100 / host>255 / path>255 → **500**(应 422)。`users/spawn_rate/duration: int` 无 `ge/gt`:传 0/负数经 API → 201(前端 `min="1"` 仅前端拦)→ 运行期传 Locust `/swarm` 异常;`duration<=0` → 空跑直接 `done`(rps/avg/fail 全 None);`target_host` 无 URL 格式校验 | schema 缺 min/max_length 与 ge/gt;model 列宽 `name(100)/host(255)/path(255)`;`s_run` 未防边界 | 用例设计新发现 | 待修复 |
| BUG-040 | P1 | Locust master 不可达 → 任务永久卡 running(无回滚);删除不校验 running | `run_task` 先 `s_mark_running`(DB 标 running 返 200),再 `run_perf_task.delay` 异步派 worker。worker `s_run` 内 `requests.post(master/swarm)`、`requests.get(/stats)`、`/stop` **均无 try**:不可达/采样异常 → 抛错、Celery 失败 → status 停在 `running`,**无 finally 回滚** → 任务永久卡。另 `db_delete` 不检查状态,删正在跑的任务 → worker 后续 `db_update` 找不到行静默结束 | `s_run` 无异常兜底/状态回滚;delete 无 running 保护 | 用例设计新发现 | 待修复 |
| BUG-046 | P1 | 压测任务无「停止/取消」能力,启动后只能等 duration 到或删除 | `POST /perf/tasks/{id}/run` 标 running 后异步跑满 `duration` 才自动 `/stop` 标 done;**中途无法人工停止**:perf 路由只有 create/get/list/delete/run,无 stop/cancel 端点;service 无停止方法;前端只有「运行/删除」按钮。叠加 BUG-040,用户一旦误启动或环境未就绪,任务就永远停不下来 | 未实现停止/取消接口;`s_run` 同步跑满 duration,无中断机制(无 celery revoke / 无标志位轮询) | 手测新发现(关联 BUG-040) | 待补 |
| BUG-047 | P1 | 压测结果不进报告、运行中前端零反馈、只存 3 标量无法定位瓶颈 | ①结果**不写 `/reports`**,去 Reports 找压测报告找不到;②结果只在 Perf 列表三列且**仅 done 后有值**,running 全 —;③前端**无图表、无 Grafana 入口、无轮询**:运行中零实时反馈,跑完不自动刷新;④结果只有 rps/平均耗时/失败率 **3 个汇总标量,无 P95/P99、无错误类型分布、无时间序列、无按接口拆分** → 无法定位瓶颈;指标覆盖式写回,不留历史时序 | 压测可观测性停留在「3 标量写回 + Prometheus 实时指标」,前端未做实时监控页/Grafana 嵌入/结果详情;无时序留存 | 手测新发现 | 待补 |

> 备注:前端已先行改善(commit `f8c5d13`):压测弹层从接口/环境选择自动带参、面板加 Locust/Grafana 外链、running 轮询自动刷新——部分缓解 BUG-047 的③。
