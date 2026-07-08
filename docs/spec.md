# WhaleTestPro 内部规格书 / 需求文档

> 版本：v1.1（2026-07-07）
> 用途：作为「测试用例设计」的输入资料。本文只描述**代码里真实存在的行为**，不臆造未实现的功能；对代码中不确定/可疑之处，统一记在文末「附录 A · 待确认问题」，不擅自补全。
> 更新（v1.1，2026-07-07）：附录 A-1（接口 URL 提示文案）已修复，从待办划出；模块 10/12 补记 07-07 前端增强（压测页接口/环境下拉自动填 + Grafana 入口 + 运行态轮询；定时调度页 tag 聚合下拉）；回归模块前端命名统一为「回归测试」。

---

## 一、系统概述

WhaleTestPro 是一个**团队协作型接口测试平台**。用户登录后，在「项目」隔离的空间内维护接口、用例、环境、场景、Mock 等资源，并可执行用例、跑回归、压测、录制/回放流量。

### 1.1 技术栈
- 后端：FastAPI + SQLAlchemy + MySQL（主库 + 影子库）
- 异步：Celery + RabbitMQ（流量录制落库）、Celery Beat（定时调度）
- 压测：Locust（master/worker）
- 监控：Prometheus + Grafana（`/metrics` 暴露指标）
- 前端：Vue 3 + Pinia
- 部署：Docker Compose（9 服务）；CI：GitHub Actions（push 触发 pytest）

### 1.2 分层架构
后端统一 5 层：`model（表）→ schema（校验）→ repository（SQL）→ service（业务）→ router（HTTP）`。

### 1.3 多租户模型（贯穿全系统）
- 除认证、项目管理、Mock 命中、demo_order 外，**几乎所有业务接口都要求 HTTP 头 `X-Project-Id`**，用于确定当前项目。
- 所有查询在 repository 层都按 `project_id` 过滤（防越权，纵深防御，不信任上层）。
- 缺 `X-Project-Id` → 422（FastAPI 缺必填 Header）；`X-Project-Id` 指向不存在的项目 → 404。

---

## 二、通用约定

### 2.1 认证
- 采用 JWT Bearer Token。除下列公开接口外，均需请求头 `Authorization: Bearer <token>`：
  - 公开：`POST /auth/register`、`POST /auth/login`、Mock 命中 `/mock/{project_id}/...`、`demo_order` 接口、`GET /health`、`/metrics`、`/docs`。
- 鉴权失败（token 无效/过期/已登出/用户不存在）→ **401**，响应头带 `WWW-Authenticate: Bearer`。

### 2.2 项目上下文
- 需要项目上下文的接口通过 `X-Project-Id` 头传入（见 1.3）。

### 2.3 通用错误码
| 码 | 含义 |
|----|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 业务校验失败（如用例关联的接口不属于当前项目）|
| 401 | 未认证 / 凭证失效 |
| 404 | 资源不存在 / 项目不存在 |
| 409 | 唯一性冲突（项目重名）|
| 422 | 请求体/头字段校验失败（Pydantic）|
| 429 | 触发频控（登录）|

---

## 三、功能模块

> 每个模块给出：数据模型 → 接口清单 → 业务规则 → 边界/异常。所有 `id` 前端不展示（防枚举，改用行序号）。

---

### 模块 1 · 认证与用户（`/auth`）

**数据模型 `users`**：`id`、`username`(唯一, ≤50)、`hashed_password`(≤200)。

**接口清单**
| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/auth/register` | 否 | 注册，入参 `{username, password}`，返回 `{id, username}` |
| POST | `/auth/login` | 否 | 登录，返回 `{access_token, token_type=bearer}` |
| POST | `/auth/logout` | 是 | 登出，把当前 token 加入黑名单 |

**业务规则**
- 密码加密存储（不落明文）。
- 登录**频控**：同一 IP `login:{ip}` 60 秒内最多 5 次，超限 → 429。
- 登出后该 token 立即失效（黑名单）：再用它访问任何需认证接口 → 401。

**边界/异常**
- 用户名重复注册：`username` 唯一约束冲突。
- 错误密码 / 不存在用户登录：登录失败。
- 无 token / 伪造 token / 过期 token 访问受保护接口 → 401。

---

### 模块 2 · 项目管理（`/projects`，多租户根）

**数据模型 `project`**：`id`、`name`(唯一, ≤100)、`description`(≤500)、`created_at`。

**接口清单**（均需登录，**不需要** `X-Project-Id`）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/projects` | 创建项目，入参 `{name, description?}` |
| GET | `/projects` | 列出所有项目 |
| GET | `/projects/{id}` | 取单个项目 |
| DELETE | `/projects/{id}` | 删除项目 |

**业务规则**
- 项目名**全局唯一**，重名 → 409（`IntegrityError` 转 409，并回滚事务）。
- 系统内置「默认项目」(id=1)，老数据迁移归属于它。

**边界/异常**
- 重名创建 → 409。
- 删除/查询不存在的项目 → 404。
- **注意：无「更新项目」接口**（见附录 A-4）。

---

### 模块 3 · 接口管理（`/interfaces`）

**数据模型 `interface`**：`id`、`name`(≤100)、`method`(≤10)、`url`(≤500)、`headers`(JSON)、`params`(JSON)、`body`(JSON)、`category`(≤50, 可空)、`project_id`。

**接口清单**（均需登录 + `X-Project-Id`）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/interfaces` | 新建接口 |
| GET | `/interfaces` | 列出当前项目接口 |
| GET | `/interfaces/{id}` | 取单个接口 |
| PUT | `/interfaces/{id}` | 全量更新接口 |
| DELETE | `/interfaces/{id}` | 删除接口 |
| PATCH | `/interfaces/categories/rename` | 批量重命名分类，入参 `{old_name, new_name}` |
| DELETE | `/interfaces/categories/{name}` | 清空某分类（把该分类下接口的 `category` 置空，不删接口）|

**业务规则**
- `url` 字段**只填路径**（如 `/orders/{id}`），执行时环境的 `base_url` 会自动拼在前面，无需在接口里写 `https://` 前缀。
- 路径参数/头/体支持 `${变量名}` 模板（执行时用环境变量或链路提参渲染）。
- `category` 是**单层字符串标签**（非独立表），前端按它分组、可折叠。
- 分类重命名/清空是**批量 UPDATE**（一条 SQL），只影响当前项目。

**边界/异常**
- 路由注册顺序：`/categories/rename`、`/categories/{name}` 必须先于 `/{interface_id}` 注册，否则 `categories` 会被当成 id 转换 → 422。
- 操作不存在接口 → 404。

---

### 模块 4 · 测试用例（`/cases`）

**数据模型 `test_case`**：`id`、`name`、`interface_id`(FK)、`expected_status`、`extract_rules`(JSON)、`assertions`(JSON)、`setup_sql`(JSON)、`teardown_sql`(JSON)、`datasets`(JSON)、`retries`(默认0)、`tags`(JSON)、`project_id`。

**接口清单**（均需登录 + `X-Project-Id`）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/cases` | 新建用例 |
| GET | `/cases` | 列出当前项目用例 |
| GET | `/cases/{id}` | 取单个用例 |
| DELETE | `/cases/{id}` | 删除用例 |
| POST | `/cases/{id}/run?env_id=` | 单跑一条用例（可选环境）|
| POST | `/cases/chain` | 链式执行，body 传 `case_ids: [int]`，可选 `env_id` |

**用例字段语义**
- `expected_status`：期望 HTTP 状态码。
- `assertions`：断言数组，逐条判定，全过才算通过。支持类型：
  | type | 判定 |
  |------|------|
  | `json_eq` | JSONPath 取值 == expected |
  | `json_contains` | expected in 取值 |
  | `json_gt` / `json_lt` | 取值 > / < expected |
  | `response_time_lt` | 响应耗时(ms) < expected |
  | `header_eq` | 响应头(path) == expected |
  | `header_contains` | expected in 响应头(path) |
  | `json_schema` | 用 JSON Schema 校验响应体 |
  | `db_eq` | 执行 `sql` 取标量 == expected |
- `extract_rules`：`{变量名: JSONPath}`，从响应提取值存入上下文（供链路后续用例引用）。
- `setup_sql` / `teardown_sql`：执行前/后跑的 SQL 列表（teardown 在 finally 中必跑）。
- `datasets`：数据驱动/参数化，每行是一组变量；有 datasets 时逐行执行，全部通过才算 passed。
- `retries`：失败重试次数（总尝试 = retries + 1，一旦通过即停）。
- `tags`：标签数组，供回归按标签筛选。

**执行逻辑（单跑 `run_case`）**
1. 取用例、取关联接口（任一缺失返回 `{"error": ...}`）。
2. 组装上下文 = 环境变量 + `base_url`。
3. 有 datasets → 逐行 `_run_with_retry`；否则单次。
4. 每次：跑 setup_sql → 渲染并发请求 → 判定状态码 + 断言 → 跑 teardown_sql。
5. 写入一条**报告**（report），记录 passed 与明细。

**链式执行（`run_chain`）**
- 按 `case_ids` 顺序依次执行；前一条用例的 `extract_rules` 提取值注入上下文，供后续用例的 `${变量}` 引用（实现接口串联/参数传递）。
- **与单跑的差异（见附录 A-2）**：链式路径**不执行 setup/teardown SQL、不做 retries、不处理 datasets、不写报告**。

**边界/异常**
- 新建用例时，`interface_id` 若不属于当前项目 → **400**（跨项目引用被拒）。
- 用例关联接口被删后再执行 → 返回 `{"error": "用例关联的接口不存在"}`。
- 断言类型未知 → 该条断言 passed=false，actual 标注「未知断言类型」。
- 断言执行异常（JSONPath 未命中/SQL 报错等）→ 该条 passed=false，actual 记错误信息。

---

### 模块 5 · 用例执行引擎附加行为

**变量模板**：`${var}` 语法（正则 `\$\{(\w+)\}`），变量缺失 → 抛 `KeyError`。JSONPath 用 `jsonpath_ng` 解析，未命中 → 抛 `KeyError`。

**熔断保护（每接口独立）**：见模块 14。请求前检查熔断器；被测下游 5xx 或连接异常记失败，2xx/3xx/**4xx 记成功**（4xx 视为「下游还活着」）。

**URL 拼装**：`base_url.rstrip('/') + '/' + path.lstrip('/')`，避免双斜杠。

---

### 模块 6 · 环境管理（`/environments`）

**数据模型 `environment`**：`id`、`name`、`base_url`(≤500)、`variables`(JSON)、`project_id`。

**接口清单**（登录 + `X-Project-Id`）：`POST` / `GET 列表` / `GET/{id}` / `PUT/{id}` / `DELETE/{id}`。

**业务规则**
- `base_url` 执行用例时自动拼到接口路径前。
- `variables` 是环境级变量字典，注入执行上下文，供 `${var}` 渲染。
- 前端「用例/场景」页支持**按项目记忆上次选择的环境**（Pinia + localStorage，键 `wtp_env_by_pid`）。

**边界/异常**：操作不存在环境 → 404。

---

### 模块 7 · 场景编排（`/scenarios`）

**数据模型 `scenario`**：`id`、`name`、`description`(≤500)、`case_ids`(JSON, **有序**用例 id 数组)、`project_id`、`created_at`。

**接口清单**（登录 + `X-Project-Id`）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/scenarios` | 新建场景 |
| GET | `/scenarios` | 列表 |
| GET | `/scenarios/{id}` | 取单个 |
| PUT | `/scenarios/{id}` | 更新（全量）|
| DELETE | `/scenarios/{id}` | 删除 |
| POST | `/scenarios/{id}/run?env_id=` | 运行场景 |

**业务规则**
- `case_ids` 存 JSON 数组、**不做外键约束**：允许用例被删后场景仍保留（前端渲染时优雅跳过孤立引用），也便于拖拽重排。
- 运行场景 = 复用 `run_chain`（按 `case_ids` 顺序链式跑，含提参传递）。
- 前端为三列布局（场景列表 / 用例库 / 编辑区），用**快照对比**做「未保存」脏检测（避免切换场景时误报）。

**边界/异常**：运行/操作不存在场景 → 404。

---

### 模块 8 · 回归测试（`/regression`）

**接口清单**（登录 + `X-Project-Id`）
| 方法 | 路径 | 入参 |
|------|------|------|
| POST | `/regression` | `case_ids?`（不传=当前项目全部用例）、`env_id?`、`tag?`（按标签筛）、`notify?`（是否飞书通知）|

**返回汇总**
- `passed`（是否全过）、`total`、`passed_count`、`failed_count`、`pass_rate`。
- 接口覆盖率：`interface_covered / interface_total`（有用例覆盖的接口数 / 项目接口总数）。
- 每条用例结果明细 `results`。

**业务规则**
- 通过率、覆盖率写入 Prometheus 指标（`regression_pass_rate`、`regression_coverage`）。
- `notify=true` 且配置了 `FEISHU_WEBHOOK` 时，推送飞书文本告警。

**边界/异常**：单条用例执行异常被捕获，记为该条 failed，不影响整体继续。

---

### 模块 9 · Mock 挡板（`/mocks` + 命中 `/mock`）

**数据模型 `mock`**：`id`、`name`、`path`(≤255)、`method`(≤10)、`status`(默认200)、`body`(JSON)、`delay_ms`(默认0)、`project_id`。

**管理接口**（登录 + `X-Project-Id`）：`POST` / `GET列表` / `GET/{id}` / `PUT/{id}` / `DELETE/{id}`。

**命中接口**（**无需认证**）
| 方法 | 路径 | 说明 |
|------|------|------|
| ANY | `/mock/{project_id}/{full_path}` | 被测系统/脚本调用，按 项目+路径+方法 匹配挡板 |

**业务规则**
- 命中路由的 `project_id` 从 **URL 前缀**取（不走 header）——面向被测系统的调用风格，对齐 Apifox/Postman Mock。
- 命中后：若配置 `delay_ms` 则先 sleep，再返回配置的 `status` + `body`。
- 未匹配到规则 → 404 `{"detail": "未匹配到挡板规则"}`。

---

### 模块 10 · 定时调度（`/schedules`）

**数据模型 `schedule`**：`id`、`name`、`cron`(≤100)、`tag`(≤50, 可空)、`enabled`(默认true)、`project_id`。

**接口清单**（登录 + `X-Project-Id`）：`POST` / `GET列表` / `GET/{id}` / `PUT/{id}` / `DELETE/{id}`。

**业务规则**
- 存储的是「定时回归」配置：按 `cron` 周期触发、按 `tag` 选用例集、`enabled` 控制启停。
- 实际触发由 Celery Beat 消费（触发机制细节见附录 A-3）。

**边界/异常**：操作不存在调度 → 404。

**前端（v1.1，07-07 增强）**：新建/编辑弹窗的 `tag` 由裸输入改为从现有用例 tag 聚合下拉选（仅前端便利，不改后端）；`cron` 提供常用频率快捷构造。

---

### 模块 11 · 测试报告（`/reports`）

**数据模型 `test_report`**：`id`、`case_id`、`passed`、`detail`(JSON)、`created_at`、`project_id`。

**接口清单**（登录 + `X-Project-Id`，**只读**）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/reports` | 列出当前项目报告 |
| GET | `/reports/{id}` | 取单个报告 |

**业务规则**
- 报告由用例执行时**自动写入**，无手动创建/删除接口。
- `detail` 存执行明细（状态码、断言结果、尝试次数等）。
- 前端待办：把「用例 {id}」展示成「用例 {name}」（见任务 #15，未完成）。

---

### 模块 12 · 压测（`/perf`）

**数据模型 `perf_tasks`**：`id`、`name`、`target_host`、`target_path`、`users`、`spawn_rate`、`duration`、`status`(默认pending)、`rps`、`avg_response_ms`、`fail_ratio`、`project_id`。

**接口清单**（登录 + `X-Project-Id`）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/perf` | 新建压测任务 |
| GET | `/perf` | 列表 |
| GET | `/perf/{id}` | 取单个 |
| DELETE | `/perf/{id}` | 删除 |
| POST | `/perf/{id}/run` | 运行压测 |

**运行逻辑**
1. 标记任务 `running`。
2. 把 `target_path` 写入 Redis（`locust:target_path`），master 在 test_start 广播给 worker。
3. 调 Locust master `/swarm`（`user_count`/`spawn_rate`/`host`）。
4. 每 2 秒采样一次 `/stats/requests`，刷新 Prometheus 指标（rps/fail_ratio/user_count/avg_response_ms）→ 实时曲线。
5. 到 `duration` 后调 `/stop`，指标清零，把最后一次采样写回任务（rps/avg/fail_ratio）、状态 `done`。

**状态机**：`pending → running → done`。

**前端（v1.1，07-07 增强）**：新建时可从接口列表选 `target_path`、从环境列表选 `target_host` 自动填入；提供 Locust / Grafana 外链入口；任务处 `running` 时前端轮询自动刷新结果。

---

### 模块 13 · 流量录制 / 回放

**录制（自动，无独立创建接口）**
- 中间件 `recording_middleware` 抄一份请求/响应，丢进 RabbitMQ，由 worker 落库（异步，录制失败绝不影响正常业务）。
- 跳过前缀：`/traffic`、`/metrics`、`/docs`、`/openapi.json`、`/static`、`/health`、`/auth`、`/projects`。
- 项目归属提取优先级：① 头 `X-Project-Id` → ② URL `/mock/{pid}/...` → ③ 兜底 pid=1。
- 敏感头会脱敏（如鉴权头存成 `***`）。

**数据模型 `traffic_records`**：`id`、`method`、`path`(索引)、`request_headers`、`request_body`、`response_status`、`response_body`、`created_at`、`project_id`。

**录制查询接口**（`/traffic`，登录 + `X-Project-Id`）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/traffic?limit=100` | 列出录制记录（默认最多 100 条）|
| GET | `/traffic/{id}` | 取单条记录 |

**回放接口**（`/replay`）
| 方法 | 路径 | 入参 |
|------|------|------|
| POST | `/replay/{record_id}` | 可选 `{env_id?, field_rules?}` |

**回放逻辑**
- 用录制的 method + body 重放到目标（不传 env 打回本机 `http://127.0.0.1:8000`）。
- 只带 `X-Shadow:1` 头（写操作落**影子库**，零污染主库），不原样带录制的旧 headers（host/content-length/脱敏鉴权头带过去无意义）。
- 逐字段 diff：录制老响应 vs 回放新响应，`field_rules` 可叠加自定义比对规则（忽略/类型/正则/容差）。
- 返回 `{recorded_status, recorded_body, replayed_status, replayed_body, diff}`。

**边界/异常**：record 不存在 → 返回 None（路由层应处理）。

---

### 模块 14 · 熔断器（内部机制）

**每个 interface.id 一个独立熔断器**，参数：`failure_threshold=5`、`recovery_timeout=10s`、`success_threshold=1`。

**状态机**
- `CLOSED`：放行。连续失败达 5 次 → `OPEN`。
- `OPEN`：快速失败（抛 `CircuitBreakerOpen`）。冷却满 10s → `HALF_OPEN`。
- `HALF_OPEN`：放试探；成功 1 次 → `CLOSED`（清零失败）；失败 1 次 → 立即回 `OPEN`。

**失败/成功判定**：下游 5xx 或连接异常 = 失败；2xx/3xx/4xx = 成功。

---

### 模块 15 · 影子隔离（内部机制）

- 请求头 `X-Shadow:1` 时，`shadow_middleware` 置影子上下文，写操作路由到**影子库**（`engine_shadow`），实现「压测/回放不污染生产数据」。
- 建表时主库、影子库都会 `create_all`。

---

### 模块 16 · demo_order（被测样例，非平台功能）

- `/demo-order`（`demo_orders` 表：`id`、`item`）：POST 创建、GET 列表，**无认证、无项目**。用作平台自测的最简被测接口。
- 另有独立 Go 服务 **WhaleShop**（同级仓库）作为跨语言被测系统（SUT），提供订单 CRUD/慢接口/错误接口，供 WhaleTestPro 做真实 HTTP 契约测试。

---

## 四、非功能性需求

- **监控**：`/metrics` 暴露 Prometheus 指标（回归通过率/覆盖率、压测 rps/耗时/失败率、各路由请求数/耗时）；Grafana 看板。
- **CI**：GitHub Actions，push 自动 checkout → 装 Python3.10 → 装依赖 → 装 pytest → 跑回归单测（当前含熔断 5 个单测）。
- **文档**：`/docs` 为本地化 Swagger UI（JS/CSS/图标走本地 `/static`，不依赖 CDN）。
- **健康检查**：`GET /health` → `{"status": "ok"}`。
- **中文编码**：MySQL 连接串带 `charset=utf8mb4`，防中文乱码。
- **安全展示**：前端所有资源列表**不展示数据库 id**，改用行序号（防枚举/IDOR）。

---

## 附录 A · 疑点确认结果与待办（2026-07-05 已与产品负责人过一轮）

| # | 疑点 | 结论 | 待办 |
|---|------|------|------|
| 1 | 变量模板 `${var}` vs URL 提示 `{{base_url}}` 不一致 | **URL 字段无需写占位符**（`base_url` 执行时自动拼接）；前端那句 `{{base_url}}` 提示是误导，要改 | ✅ 已修复（`64c5cc8`）：提示改为「只填路径，环境前缀由 base_url 自动补」，`save()` 强制 `/` 开头（对应 BUG-016）|
| 2 | 链式执行(`run_chain`) 不写报告，与单跑不一致 | **场景/链路跑完也要落报告** | 【后端】`run_chain` 补写 report（对齐 `run_case`）|
| 3 | 定时调度触发机制 | **已确认，实现正确**：用 RedBeat（Redis 存储）。`enabled=false` → 删除 RedBeat 条目（真停用）；create/update → 重新 `sync_schedule`（改 cron 热生效）；delete → 移除条目。**边界坑**：`_parse_cron` 用 `cron.split()` 硬拆 5 段，非标准 5 段 cron → `ValueError` → 500 | 测试用例覆盖「非法 cron → 500」负向点 |
| 4 | 项目无「更新」接口 | **需要补**：`/projects` 要能改名/改描述 | 【后端】新增 `PUT /projects/{id}` |
| 5 | 流量回放 `_base_url` 少传 `project_id` | **确认是 Bug**：`traffic_replay.py:12` 调 `env_repo.db_get(db, env_id)`，但现签名是 `(db, env_id, project_id)`，指定环境回放必崩（同 #20）。且 `/replay` 链路当前无项目上下文 | 【后端】修复；并决定回放是否引入项目隔离 |
| 6 | Mock 命中匹配精确度 | **现状=精确匹配**（`Mock.path == path`，无通配，多命中取第一条）。**已定：加 `{参数}` 路径通配**，匹配优先级「精确 > 通配」 | 【后端】`db_match` 支持路径参数（`/orders/{id}` 命中 `/orders/123`）+ 精确优先 |
| 7 | 断言 `db_eq` 可执行任意 SQL | **确认危险，需限制只读**（仅允许 SELECT）| 【后端】`db_eq` 加 SQL 白名单/只读校验；测试用例覆盖「塞危险 SQL 被拒」|

> 说明：后端改动按项目约定由本人手敲，前端改动由 Claude 代写。以上待办不在本文档范围内实施，仅作记录，供测试用例设计时把「已知 Bug / 待补功能」也纳入覆盖。
