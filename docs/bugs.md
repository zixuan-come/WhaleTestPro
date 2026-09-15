# WhaleTestPro 缺陷记录（Bug Tracker）
## 当前状态总览（2026-09-08）

> 本节是当前开发依据。下方的历史缺陷表保留用于追溯，其中部分”待修复”记录已在后续开发中完成，不应直接当作当前待办。

### 已完成（代码已实现并通过验证）

**2026-09-08 P0/P1/P2 修复批次：**
- ✅ **P0 安全修复（6个）**：SQL 注入防护、并发竞态、流量回放项目隔离、压测任务隔离、Docker 端口暴露、Grafana 匿名访问
- ✅ **SQL 信任边界收紧**：`db_eq` 断言限制为单条只读 SELECT；setup/teardown SQL 允许 INSERT/UPDATE/DELETE、禁止 DDL(DROP/TRUNCATE/ALTER)、禁止多语句、禁止注释绕过、UPDATE/DELETE 强制带 WHERE、禁止修改平台业务表；40 个 P0 安全测试全部通过
- ✅ **P1 功能修复（全部）**：字段校验、Mock 通配、压测停止、环境校验、调度回滚、报告分页等
- ✅ **P2 体验优化（可修复项）**：接口直接执行、登录校验、回归明细优化、文档路由等
- ✅ **测试覆盖**：40 个 P0 安全测试全部通过，108 个后端测试全部通过（含测试套件 26 个：14 schema + 12 service）
- ✅ **服务验证**：Docker Compose 所有服务正常运行，前端构建成功

**2026-09-08 产品演进 + 架构线补齐：**
- ✅ **回归/场景统一测试套件模型（BUG-045）**：新增 `TestSuite` 资源（模型/schema/repo/service/router 六件套），把「散装回归用例」与「场景链」统一为一个可运行单元；套件可含 scenario_ids + case_ids + tags，支持手动运行与定时调度（schedule 表加 `suite_id`，优先级高于 tag）；报告表加 `suite_id/suite_name/execution_type` 记录套件维度；前端 `TestSuites.vue` 卡片网格布局，一屏对比多套件；DB 迁移 `migrations/001_add_test_suite.sql` 已在容器库执行验证。详见 `docs/test_suite_implementation.md`
- ✅ **架构线 D（#21）Shell 脚本落地**：`scripts/analyze_log.sh`（Nginx 访问日志分析：QPS/状态码分布/Top URL·IP/错误摘要/慢请求 rt 筛选 + P50·P95·P99 分位，沉淀 study 7.2 文本三剑客技能）、`scripts/healthcheck.sh`（全栈健康巡检：容器状态/后端 HTTP/中间件 ping/磁盘水位，退出码=异常项数，cron 友好）；配套给 `frontend/nginx.conf` 加 `timed` 日志格式（带 rt=请求耗时）。两脚本均已实测通过
- ✅ **架构线 E（#22）K8s manifest 落地**：`k8s/` 下 9 服务全量转译（namespace/secret/configmap/PVC + StatefulSet(mysql) + Deployment×8 + Service），compose→K8s 映射心智齐全（有状态用 StatefulSet+PVC、depends_on 用 initContainer、named volume 用 PVC、--scale 用 replicas）；`kubectl apply --dry-run=client -f k8s/` 全 22 资源校验通过

**历史完成项：**
- 接口管理搜索（BUG-017）：支持按名称、URL、请求方法和分类过滤；
- 接口管理页直接执行接口（BUG-018）：支持选择环境、执行按钮和结果弹窗；
- 接口字段严格校验（BUG-025）：method、URL、分类已做规范化、长度和格式校验；
- 场景描述长度校验（BUG-030）：description 最长 500 字符；
- 链路报告（BUG-009）：直接 `/cases/chain` 按步骤写入普通测试报告，场景执行写入场景报告，并有 HTTP 黑盒回归；
- 压测可观测性（BUG-047）：支持 RPS、平均耗时、P95、P99、失败率、按请求统计、错误分布、历史采样和趋势图；
- Mock 路径参数通配、调度字段校验及相关测试已完成。

### 仍未完成

| 优先级 | 任务 | 当前说明 |
|---|---|---|
| P2 | 用户功能验收 | 自动化测试和服务连通性已通过，团队、接口直接执行、场景报告、压测监控、接口引用迁移等页面仍需用户按真实流程验收。 |

### 产品待定

| 任务 | 当前说明 |
|---|---|
| （暂无） | 原「回归/场景统一测试套件模型（BUG-045）」已于 2026-09-08 实现并通过验证，移至上方已完成区。 |

### 当前工作区与文档状态说明

- 本文档历史表保留原始现象和根因，用于追溯；表格最后一列“状态”才是当前判断依据。
- 已修复条目不应重新列入待办；`BUG-045` 已于 2026-09-08 实现并通过验证（不再是产品待定）；BUG-009、BUG-047、BUG-021 已完成并通过回归验证。
- 当前工作区存在多批历史未提交代码、测试和文档修改，不能将其全部归因于本轮文档整理，也不能在本轮自动提交。
- 具体提交范围以 `git status --short` 和 staged diff 为准；`app/routers/interface.py.bak` 为未跟踪备份文件，禁止误删或提交。
> 版本：v1.0（2026-07-05）
> 用途：记录平台自测（用例设计过程）中发现的缺陷，以及此前开发/联调阶段已修复的问题。
> 严重度：P0 阻断 / P1 严重 / P2 一般。
> 状态：已修复 / 待修复 / 待补 / 待做。
> 说明：本文档只记录**代码里真实存在**的缺陷；每条给出现象、根因、来源（提交号或 spec 附录条目）。
> 按模块视图：本表为全量总账，另在 [`docs/测试缺陷/`](测试缺陷/) 下按「模块 → 功能测试Bug / 接口测试Bug」拆分归档，便于按功能定位。

---

## 一、已修复（Fixed）

| 编号 | 严重度 | 模块 | 标题 | 现象 | 根因 | 修复提交 |
|------|--------|------|------|------|------|----------|
| BUG-001 | P2 | 前端·登录 | 登录页缺「注册」入口 | 新用户在登录页找不到注册入口 | 页面漏做跳转入口 | `5b13b7d` |
| BUG-002 | P2 | 前端·登录 | 密码「眼睛」显示态下提交失败后不复位 | 明文态提交失败，输入框状态残留 | 提交失败未复位显隐态 | `5b13b7d` |
| BUG-003 | P1 | 前端·各资源页 | 资源页只有新建+删除，缺编辑 | 建错的记录只能删了重建 | 编辑功能未实现 | 已修复 |
| BUG-004 | P0 | 后端·执行引擎 | 跑用例 500：`_env_context` 少传 `project_id` | 指定环境跑用例直接崩 | `env_repo.db_get` 签名升为 3 参后调用点漏传 `project_id` | `c241b10` |
| BUG-005 | P1 | 部署·E2E | compose 漏 `SHADOW_DATABASE_URL`、vite 代理端口对不上 | E2E 环境起不来/前端打不通后端 | 编排配置缺项 | 已修复 |
| BUG-006 | P1 | 后端·DB | 中文乱码（mojibake） | 中文写库后读出乱码 | 连接串缺 `charset=utf8mb4` | 已修复 |
| BUG-007 | P1 | 前端·安全 | 资源列表暴露 DB `id`（IDOR/枚举风险） | 前端直接展示自增 id，可枚举/越权探测 | 列表渲染用了 DB id | `a7950c2`（改用行序号） |

---

## 二、历史缺陷明细（状态字段为准）

> 分工约定：后端由本人手敲；前端由 Claude 代写。以下按 spec 附录 A + 用例设计新发现汇总。

| 编号 | 严重度 | 模块 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|------|
| BUG-008 | P0 | 后端·流量回放 | 指定 env 回放必崩 | 传 `env_id` 回放时 `TypeError` | `traffic_replay.py:12` `_base_url` 调 `env_repo.db_get(db, env_id)` 少传 `project_id`（签名已是 3 参）；且 `/replay` 链路无项目上下文 | spec A-5 | 已修复 |
| BUG-009 | P1 | 后端·用例执行 | `run_chain` 跑完不落报告 | 直接链路按步骤写入普通测试报告；场景执行写入场景报告 | `run_chain` 已分别支持普通报告和场景报告 | spec A-2 | 已修复 |
| BUG-010 | P1 | 后端·项目管理 | 缺 `PUT /projects/{id}` | 项目无法改名/改描述 | 未实现更新接口 | spec A-4 | 已修复 |
| BUG-011 | P1 | 后端·Mock | Mock 仅精确匹配，无路径参数通配 | `/orders/{id}` 命不中 `/orders/123` | `db_match` 用 `Mock.path == path` 硬等 | spec A-6 | 已修复 |
| BUG-012 | P0 | 安全·断言 | `db_eq` 可执行任意 SQL | 断言里可塞 `DELETE`/`DROP` 等，无只读限制 | `db.execute(text(sql))` 不校验 | spec A-7 | 已修复 |
| BUG-013 | P0 | 注册·账号校验 | 账号长度未按需求 4–20 校验 | 需求账号 4–20 位，但 <4、(20,50] 均被接受注册（应 422）；>50 触发 DB `Data too long`→**500**；含空账号 | 前端 Login.vue 输入框无 `minlength/maxlength`；后端 schema `username: str` 无 `min/max_length`，落 DB `String(50)` 才报错 | 用例设计新发现 | 已修复 |
| BUG-014 | P1 | 注册·密码校验 | 密码长度缺少边界校验 | 原规则为 8–20 位；2026-09-18 产品口径调整为 4–20 位，空、<4、>20 均应返回 422 | 前后端曾缺少一致的密码长度校验 | 用例设计新发现 | 已修复（现行规则 4–20 位） |
| BUG-015 | P1 | 后端·调度 | 非法 cron → 500，且留孤儿行/状态不一致 | `_parse_cron` 用 `cron.split()` 硬拆 5 段，非标准段数 → 解包 `ValueError` → 500（应 422）；段数够但值越界（如 `99 2 * * *`）→ celery `crontab()` 也 `ValueError` → 500。**更深**：`s_create` 先 `db_create`（commit 落库）再 `sync_schedule`，故非法 cron 时 **DB 行已建成、RedBeat 未注册** → 返 500 但库里留孤儿行，状态不一致；`enabled=False` 时 `sync_schedule` 早返回**不解析** → 非法 cron 可静默建成（埋雷），之后 PUT 翻 `enabled=True` 才 500（此时 enabled 已 commit 成 True，但实际未调度）| `_parse_cron` 未校验段数/取值；service 落库与同步非原子、无回滚 | spec A-3 边界 | 已修复 |
| BUG-016 | P2 | 前端·接口 | URL 输入框 `{{base_url}}` 提示误导 | 提示让用户以为要写占位符，实际 `base_url` 执行时自动拼 | 提示文案错误 | spec A-1 | 已修复（工作区待提交）：提示改为「只填路径，环境前缀由 base_url 自动补」+ `save()` 强制 `/` 开头 |
| BUG-017 | P2 | 前端·接口 | 接口管理搜索未做 | 接口多时无法检索 | 功能未实现 | task#6 | 已修复 |
| BUG-018 | P2 | 前端·接口 | 接口管理页不能直接执行接口 | 只能建/改/删，无法在页内发起调用 | 功能未实现 | task#7 | 已修复 |
| BUG-019 | P2 | 后端·注册 | `/auth/register` 创建成功返回 200，偏离 201 约定 | 其余 8 个创建接口（case/environment/perf/interface/mock/project/scenario/schedule）均显式 `status_code=201`，唯 register 未设 → 默认 200 | router 该行缺 `status_code=201` 参数 | 用例设计新发现 | 已修复 |
| BUG-020 | P2 | 前端·注册 | 注册表单无长度约束、纯空格账号可提交 | 账号/密码输入框无 `minlength/maxlength`；`onSubmit` 只判 `!username`（空串拦截），纯空格串判定为「非空」→ 放行提交 | Login.vue 前置校验只做 falsy 判断，未 trim、未限长 | 用例设计新发现 | 已修复 |
| BUG-021 | P2 | 需求·账号规则 | 账号 trim 规则 / 字符集规则未定义 | 账号含首尾空格是否 trim、是否限字母数字下划线、是否允许 emoji/特殊字符，均无明确规则；现状前后端原样接受 | spec 未定义账号字符集与 trim 策略 | 用例设计新发现 | 已修复（方案1 严格规则：trim+小写、4-20 位、仅字母数字下划线连字符且以字母数字开头、拒纯数字；repo 大小写不敏感查找兼容老用户；前后端一致，2026-09-08） |
| BUG-022 | P0 | 后端·注册并发 | 并发同名注册 → 500 | 高并发下两请求同时过 `s_register` 的「预查不存在」判断，随后双双 INSERT，第二条命中 `username` 唯一约束 → `IntegrityError` 未被捕获 → 500（应 400「用户名已存在」）| `s_register` 是 check-then-insert 非原子；`users.username unique=True`（model 确认）；service 未 try 捕获 `IntegrityError` 转 400 | 用例设计新发现 | 已修复 |
| BUG-023 | P1 | 后端·项目 | 项目 name/description 无长度校验、空名可建 | schema 
ame: str` / `description: str\|None` 无 `min/max_length`；空名经 API → 201 建成空名项目；name >100 → DB `Data too long` → **500**；description >500 → **500**（应 422）| model 
ame String(100)` / `description String(500)`，落 DB 才报错；前端 Projects.vue 建项目输入框无 `maxlength`（但已 trim 拦空）| 用例设计新发现 | 已修复 |
| BUG-024 | P1 | 后端·项目删除 | 删除挂有子资源的项目 → 500；删默认项目致孤儿 | `interface.project_id = ForeignKey("project.id")` 无级联；删一个仍挂着接口/用例的项目 → FK 约束（MySQL 1451）→ `IntegrityError`，但 `delete_project` 路由**未捕获**（对比 `create_project` 有 catch）→ 500（应先校验/级联/软删并给清晰提示）；删内置默认项目 id=1 会让迁移老数据变孤儿 | `db_delete` 直接 `db.delete+commit` 无子资源检查；delete 路由缺 `IntegrityError` 处理 | 用例设计新发现 | 已修复 |
| BUG-025 | P1 | 后端·接口 | 接口 name/method/url/category 无长度校验、空必填可建 | schema 各字段 `str` 无 `min/max_length`；空 name/method/url 经 API → 201 建成空字段接口；name>100 / method>10 / url>500 / category>50 → DB `Data too long` → **500**（应 422）| model 列宽 
ame(100)/method(10)/url(500)/category(50)`，落 DB 才报错；前端 Interfaces.vue 输入框无 `maxlength`（但已拦空 name/url）| 用例设计新发现 | 已修复 |
| BUG-026 | P1 | 后端·用例 | 用例 name 无长度校验、空名可建、超长 → 500 | schema 
ame: str` 无 `min/max_length`；空 name 经 API → 201；name>100 → DB `Data too long` → **500**（应 422）| model 
ame String(100)`，落 DB 才报错；前端 Cases.vue 已拦空 name（但无 `maxlength`）| 用例设计新发现 | 已修复 |
| BUG-027 | P1 | 后端·断言/链路 | 断言缺 `type` 键：单跑记 failed，链路直接 500（不一致）| `assertions.py:9` `a_type = a["type"]` 在 try 外；`run_case` 的 `_run_once` 整体 try 捕获 → 该次 failed；但 `run_chain:78` 调 `run_assertions` **不在 try 内** → `KeyError` 冒泡 → **500**。同理 `run_chain:82` `response.json()` 非 JSON 响应也 500 | `run_chain` 未像 `run_case` 那样包裹断言/取值异常 | 用例设计新发现（关联 BUG-009）| 已修复 |
| BUG-028 | P2 | 后端·用例执行 | `retries` 负数 → `UnboundLocalError` → 500 | schema `retries: int\|None=0` 无 `ge=0`；传 `retries=-1` → `_run_with_retry` `attempts=(-1)+1=0` → `for i in range(0)` 不进循环 → 末尾 `result["attempts"]` 引用未定义 `result` → `UnboundLocalError` → **500**（应 422 或按 0 处理）| schema 无下界校验；`_run_with_retry` 未防 attempts≤0；前端 `retries` 输入 `min="0"`（仅前端拦）| 用例设计新发现 | 已修复 |
| BUG-029 | P1 | 后端·环境 | 环境 name/base_url 无长度校验、超长 → 500；base_url 无格式校验 | schema `EnvironmentCreate` 
ame/base_url: str` 无 `min/max_length`；name>100 / base_url>500 → DB `Data too long` → **500**（应 422）；base_url 无 URL 格式校验，可存非法串（执行时拼接产异常）| model 
ame String(100)` / `base_url String(500)`；前端 Environments.vue 已 trim 拦空但无 `maxlength`、无 URL 格式校验 | 用例设计新发现 | 已修复 |
| BUG-030 | P1 | 后端·场景 | 场景 name/description 无长度校验、空名可建、超长 → 500；前端编辑区空名静默兜底 | schema `ScenarioCreate` 
ame/description: str` 无 `min/max_length`；空 name 经 API → 201；name>100 / description>500 → DB `Data too long` → **500**（应 422）；前端新建弹窗拦空名，但编辑区 `saveCurrent` 空名兜底 `'未命名'`（不拦、静默改，两处不一致）| model 
ame String(100)` / `description String(500)`，落 DB 才报错；前端 Orchestration.vue 无 `maxlength` | 用例设计新发现 | 已修复 |
| BUG-031 | P1 | 后端·回归 | 接口覆盖率可 >100%（含已删接口的幽灵 id） | `run_regression` 覆盖率 `covered_ids = {c.interface_id for 全部用例}` 未与当前接口列表取交集；用例关联的接口被删后 `interface_id` 仍在，计入 `interface_covered`，而 `interface_total` 只数当前接口 → `covered > total` → 覆盖率 >100%（如 3/2=150%）；且指定 `case_ids`/`tag` 子集时覆盖率仍按全项目用例算，与本次 `pass_rate` 范围语义不一致 | `covered_ids` 应与 `all_interfaces` 的 id 取交集；覆盖率口径需明确「项目级 vs 本次运行」 | 用例设计新发现 | 已修复 |
| BUG-032 | P2 | 前端·回归 | 回归明细展示 DB `case_id`（IDOR/枚举风险） | Regression.vue 明细行 `#{{ r.case_id }}` 直接渲染后端返回的 DB 自增 `case_id`，违反 spec「前端不展示 DB id、改用行序号」（同 BUG-007 家族）；且只显示 id 不显示用例名，可读性差（呼应模块11 报告页 `用例{id}→用例{name}` 待办）| 明细未做 id 脱敏/行序号化，也未 join 用例名 | 用例设计新发现 | 已修复 |
| BUG-033 | P1 | 后端·Mock | 挡板 name/path/method 无长度校验、空必填可建、超长 → 500 | schema `MockCreate` 
ame/path/method: str` 无 `min/max_length`；空 name/path 经 API → 201（前端 Mocks.vue 已 trim 拦 name/path 空，但 API 层不拦）；name>100 / path>255 / method>10 → DB `Data too long` → **500**（应 422）| model 列宽 
ame(100)/path(255)/method(10)`，落 DB 才报错；前端无 `maxlength` | 用例设计新发现 | 已修复 |
| BUG-034 | P2 | 后端·Mock 命中 | 命中期健壮性：delay_ms 负数 / status 非法码 → 命中 500；method 大小写敏感、path 需自带前导 `/` | schema `delay_ms: int` 无 `ge=0`：传负数经 API 建成，命中时 `time.sleep(负)` → `ValueError` → **500**（前端 `min="0"` 仅前端拦）；`status: int` 无范围校验：非法码（<100 或 >599/负数）→ `JSONResponse(status_code=非法)` 命中时 Starlette 报错 → 500；`db_match` 用 `Mock.method == method` 大小写敏感，API 层建小写 method 命不中大写请求；`path` 命中查 `"/"+full_path`，建挡板 path 未带前导 `/`（前端不强制）则命不中（关联 BUG-011 匹配精度家族）| schema 缺 delay_ms/status 范围校验；命中匹配大小写/前缀敏感 | 用例设计新发现 | 已修复 |
| BUG-035 | P1 | 后端·调度 | 调度 name/cron/tag 无长度校验、空名可建、超长 → 500 | schema `ScheduleCreate` 
ame/cron: str`、`tag: str\|None` 无 `min/max_length`；空 name 经 API → 201（前端 Schedules.vue 已 trim 拦空 name/cron，但 API 层不拦）；name>100 / cron>100 / tag>50 → DB `Data too long` → **500**（应 422）| model 列宽 
ame(100)/cron(100)/tag(50)`，落 DB 才报错；前端无 `maxlength` | 用例设计新发现 | 已修复 |
| BUG-036 | P2 | 前端·报告 | 报告列表展示 DB `case_id`、且未 join 用例名（IDOR/枚举 + 可读性差） | `Reports.vue:82` `用例 {{ r.case_id }}` 直接渲染后端返回的 DB 自增 `case_id`，违反 spec「前端不展示 DB id、改用行序号」（同 BUG-007/BUG-032 家族）；虽行首已 `#{{ i+1 }}` 行号，但紧接着又显示原始 `case_id`；且只显数字不显用例名，正是 spec 模块11 / task#15「用例{id}→用例{name}」未完成项 | 明细未做 id 脱敏，也未 join 用例名 | 用例设计新发现（关联 task#15、BUG-032）| 已修复 |
| BUG-037 | P2 | 后端·报告 | `/reports` 列表无分页/limit，报告 append-only 累积后全量返回 | `report_repo.db_list` `filter(project_id).order_by(id.desc()).all()` 无 `limit`/分页；报告由每次执行自动写入且**无删除接口**（只读模块），长期运行后单项目报告可成千上万，列表接口一次性全量返回 → 响应体膨胀、前端渲染压力（对比 `/traffic?limit=100` 有默认上限）| `db_list` 缺 `limit`/分页参数；无归档/清理机制 | 用例设计新发现 | 已修复 |
| BUG-038 | P2 | 文档·压测 | spec 模块12 路由写 `/perf`，实际代码/前端均为 `/perf/tasks` | spec 模块12 接口清单写 `POST /perf`、`GET /perf`、`POST /perf/{id}/run` 等；但 `perf.py` router `prefix="/perf/tasks"`，前端 `api/perf.js` 也用 `/perf/tasks`。**代码与前端一致、唯 spec 文档写错**（附录声明"只描述真实行为"，此处违背）| spec 文档笔误，路由前缀漏 `/tasks` 段 | 用例设计新发现 | 已修复 |
| BUG-039 | P1 | 后端·压测 | 压测字段无长度/范围校验、空必填可建、超长/负数 → 500 或运行期异常 | schema `PerfTaskCreate` 
ame/target_host/target_path: str` 无 `min/max_length`：空经 API → 201；name>100 / host>255 / path>255 → DB `Data too long` → **500**（应 422）。`users/spawn_rate/duration: int` 无 `ge/gt`：传 0/负数经 API → 201（前端 `min="1"` 仅前端拦）→ 运行期 `users<=0` 传 Locust `/swarm` 异常；`duration<=0` → `while elapsed<duration` 不进循环 → 空跑直接 `done`（rps/avg/fail 全 None）；`duration` 超大无上限 → worker 长时间占用；`target_host` 无 URL 格式校验，非法值传 Locust 运行期报错 | schema 缺 min/max_length 与 ge/gt；model 列宽 
ame(100)/host(255)/path(255)`；`s_run` 未防边界 | 用例设计新发现 | 已修复 |
| BUG-040 | P1 | 后端·压测 | Locust master 不可达 → 任务永久卡 running（无回滚）；删除不校验 running | `run_task` 路由先 `s_mark_running`（DB 标 running 并返回 200），再 `run_perf_task.delay` 异步派 worker。worker `s_run` 内 `requests.post(master/swarm)`、`requests.get(/stats)`、`/stop` **均无 try**：master/worker 不可达或采样异常 → 抛错、Celery 任务失败 → status 停在 `running`，**无 finally 回滚 pending/failed** → 任务永久卡运行中。另 `db_delete` 不检查状态，删正在跑的任务 → worker 后续 `db_update` 找不到行返回 None 静默结束，指标可能卡在最后值（未走结尾清零）| `s_run` 无异常兜底/状态回滚；delete 无 running 保护 | 用例设计新发现 | 已修复 |
| BUG-041 | P2 | 文档·流量 | spec 模块13 路由与代码不符（`/traffic`→`/traffic/records`、`/replay`→`/traffic/replay`）| spec 模块13 写 `GET /traffic?limit=100`、`GET /traffic/{id}`、`POST /replay/{record_id}`；实际 `traffic_record.py` router `prefix="/traffic/records"`、`traffic_replay.py` router `prefix="/traffic/replay"`。前端 `api/traffic.js` 对齐实际路径，唯 spec 文档写错（同 BUG-038 家族）| spec 文档笔误，路由前缀漏 `/records`、`/replay` 前缺 `/traffic` | 用例设计新发现 | 已修复 |
| BUG-042 | P0 | 后端·回放 | 任何回放都 500（record 查询少传 project_id）；且回放无认证/无项目隔离（IDOR）| `traffic_replay.s_replay:25` 调 `traffic_record_repo.db_get(db, record_id)` **少传 project_id**（repo 签名 `(db, record_id, project_id)` 3 参）→ `TypeError` → **500**，且发生在 `_base_url` 之前，故**不指定 env 的回放也必崩**（比 BUG-008 更早、更普遍，BUG-008 的 env 崩点被此掩盖）。另 `traffic_replay` 路由**无 `get_current_project`、无认证依赖** → 回放接口无项目隔离、无鉴权：修好 db_get 后仍可越权回放任意项目的 record（IDOR）| s_replay record 查询漏传 project_id；replay 路由缺认证与项目上下文 | 用例设计新发现（关联 BUG-008、spec A-5）| 已修复 |
| BUG-043 | P2 | 后端·录制 | 数组响应体因 schema 限 `dict` 被静默丢弃、录不进库 | `recording_middleware` 抄响应体后构造 `TrafficRecordCreate(response_body=_safe_json(resp_body), ...)`，但 schema `response_body: dict\|None`；所有 GET 列表接口（`/cases`、`/interfaces` 等）返回 **JSON 数组** → `_safe_json` 得 `list` → Pydantic 校验失败抛错 → 被中间件 `except Exception: pass` **静默吞掉** → 该条流量永远录不进；`request_body` 为数组同理丢弃 | schema `request_body/response_body` 只接受 `dict`，未含 `list`；中间件吞异常掩盖了丢数据 | 用例设计新发现 | 已修复 |
| BUG-044 | P2 | 文档·被测样例 | spec 模块16 路由写 `/demo-order`，实际代码为 `/demo/orders`；POST 返 200 非 201 | spec 模块16 写 `/demo-order`（POST/GET）；实际 `demo_order.py` router `prefix="/demo/orders"`，POST 无 `status_code=201`（默认 200）。demo_order 为被测样例（无认证/无项目/无前端页），路由偏差属文档笔误（同 BUG-038/041 家族）| spec 文档笔误；被测样例接口未设 201（可接受，非平台约定）| 用例设计新发现 | 已修复 |
| BUG-045 | P2 | 产品设计·回归/场景 | 回归与场景两条路割裂，不符合 Apifox「场景即运行单元」心智 | `run_regression` 只按 `case_ids`/`tag`/全部跑散用例（前端仅暴露 tag+全部），走 `run_case`（逐条独立、写报告、算通过率+覆盖率）；`scenario` 另起一条路，运行走 `run_chain`（链式提参；场景报告已支持，仍无 setup/teardown/retries）。二者不互通：**场景不能作为回归的运行范围**。对标 Apifox：测试场景既是编排单元也是自动化/回归的运行单元，tag 只是筛选辅助，无独立「回归」概念。演进方向：回归重定位为「接口自动化」，运行单元改为选场景（或场景集/套件），tag 降级为筛选，场景报告已支持；是否把直接链路调用也统一落普通报告，待产品决定。**定时调度同源**：`schedule` 表存 `cron+tag`，到点跑 `run_regression(project_id, tag)`（`scheduler.py:28`），即"定时回归"，运行单元同样是"一批用例"而非单接口——故不宜套压测的"选接口"，应随本条一起演进为"定时选场景"。前端已先行小改善：Schedules.vue 的 tag 由裸输入改为**从现有用例 tag 聚合下拉选**（不改后端） | 产品把「回归」与「场景」设计成两条不相干链路；缺「测试套件」概念 | 用例设计新发现（产品对标 Apifox）| 已完成（2026-09-08：新增 TestSuite 六件套统一 scenario+case+tag 为运行单元，接入定时调度与报告维度，前端卡片网格；26 个套件测试全绿，详见 docs/test_suite_implementation.md）|
| BUG-046 | P1 | 后端·压测 | 压测任务无「停止/取消」能力,启动后只能等 duration 到或删除 | 压测 `POST /perf/tasks/{id}/run` 标 running 后异步跑满 `duration` 才自动 `/stop` 标 done；**中途无法人工停止**：perf 路由只有 create/get/list/delete/run,**无 stop/cancel 端点**;service 无停止方法;前端 Perf.vue 只有「运行/删除」按钮,运行中时运行键 disabled。`s_run` 里那个 `requests.get(/stop)` 是 duration 到点自动调 Locust,非用户可触发。叠加 BUG-040(Locust master 不可达→requests 抛错→任务永久卡 running 无回滚),用户一旦误启动或环境未就绪,任务就永远停不下来,只能删除(而删除又不校验 running,见 BUG-040) | 未实现停止/取消接口;`s_run` 同步跑满 duration,无中断机制(无 celery revoke / 无标志位轮询) | 手测新发现(关联 BUG-040)| 已修复 |
| BUG-047 | P1 | 压测·可观测性 | 压测结果不进报告、运行中前端零反馈、只存 3 标量无法定位瓶颈 | ①压测结果**不写 `/reports`**(测试报告页是用例执行的,压测无关),用户去 Reports 找压测报告找不到;②压测结果只在 Perf 列表三列(rps/avg/fail)且**仅 done 后有值**,running 全 —;③前端**无图表、无 Grafana 入口、无轮询**(grep 全前端零匹配):运行中零实时反馈,跑完 done 也不自动刷新,需手动刷新页面才看到结果;实时曲线按设计在 Grafana(Prometheus 指标)但前端未做入口;④结果只有 rps/平均耗时/失败率 **3 个汇总标量,无 P95/P99、无错误类型分布、无时间序列、无按接口拆分** → 无法定位瓶颈;指标覆盖式写回 perf_task,不留历史时序,无法回看 | 压测可观测性停留在「3 标量写回 + Prometheus 实时指标」,前端未做实时监控页/Grafana 嵌入/结果详情;无时序留存 | 手测新发现 | 已修复 |

---

## 附：严重度判定口径
- **P0**：数据损坏/安全越权/核心链路崩溃（如任意 SQL、指定 env 回放必崩）。
- **P1**：功能缺失或行为不一致，影响可用性但有绕行（如缺更新接口、报告缺失）。
- **P2**：体验/提示/易用性问题，不影响主流程。
