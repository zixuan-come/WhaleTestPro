# 流量录制回放 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-008 | P0 | 指定 env 回放必崩 | 传 `env_id` 回放时 `TypeError` | `traffic_replay.py:12` `_base_url` 调 `env_repo.db_get(db, env_id)` 少传 `project_id`(签名已是 3 参);且 `/replay` 链路无项目上下文 | spec A-5 | 待修复 |
| BUG-041 | P2 | spec 模块13 路由与代码不符(`/traffic`→`/traffic/records`、`/replay`→`/traffic/replay`) | spec 写 `GET /traffic?limit=100` 等;实际 `traffic_record.py` router `prefix="/traffic/records"`、`traffic_replay.py` router `prefix="/traffic/replay"`。前端对齐实际路径,唯 spec 文档写错(同 BUG-038 家族) | spec 文档笔误 | 用例设计新发现 | 待修(改文档) |
| BUG-042 | P0 | 任何回放都 500(record 查询少传 project_id);且回放无认证/无项目隔离(IDOR) | `traffic_replay.s_replay:25` 调 `traffic_record_repo.db_get(db, record_id)` **少传 project_id**(repo 签名 3 参)→ `TypeError` → **500**,且发生在 `_base_url` 之前,故**不指定 env 的回放也必崩**(比 BUG-008 更早更普遍)。另 `traffic_replay` 路由**无认证依赖、无项目上下文** → 修好 db_get 后仍可越权回放任意项目 record(IDOR) | s_replay record 查询漏传 project_id;replay 路由缺认证与项目上下文 | 用例设计新发现(关联 BUG-008、spec A-5) | 待修复 |
| BUG-043 | P2 | 数组响应体因 schema 限 `dict` 被静默丢弃、录不进库 | `recording_middleware` 构造 `TrafficRecordCreate(response_body=_safe_json(resp_body), ...)`,但 schema `response_body: dict\|None`;所有 GET 列表接口返回 **JSON 数组** → `_safe_json` 得 `list` → Pydantic 校验失败 → 被中间件 `except Exception: pass` **静默吞掉** → 该条流量永远录不进;`request_body` 为数组同理 | schema `request_body/response_body` 只接受 `dict`,未含 `list`;中间件吞异常掩盖了丢数据 | 用例设计新发现 | 待修复 |
