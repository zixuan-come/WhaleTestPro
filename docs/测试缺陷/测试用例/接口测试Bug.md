# 测试用例 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。含用例、执行引擎、断言/链路。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-004 | P0 | 跑用例 500:`_env_context` 少传 `project_id` | 指定环境跑用例直接崩 | `env_repo.db_get` 签名升为 3 参后调用点漏传 `project_id` | 开发/联调 | 已修复 `c241b10` |
| BUG-009 | P1 | `run_chain` 跑完不落报告 | 场景/链路执行后无报告记录,与单跑不一致 | `run_chain` 未对齐 `run_case` 写 report | spec A-2 | 待修复 |
| BUG-012 | P0 | `db_eq` 可执行任意 SQL | 断言里可塞 `DELETE`/`DROP` 等,无只读限制 | `db.execute(text(sql))` 不校验 | spec A-7 | 待修复 |
| BUG-026 | P1 | 用例 name 无长度校验、空名可建、超长 → 500 | schema `name: str` 无 `min/max_length`;空 name 经 API → 201;name>100 → DB `Data too long` → **500**(应 422) | model `name String(100)`,落 DB 才报错;前端 Cases.vue 已拦空 name(但无 `maxlength`) | 用例设计新发现 | 待修复 |
| BUG-027 | P1 | 断言缺 `type` 键:单跑记 failed,链路直接 500(不一致) | `assertions.py:9` `a_type = a["type"]` 在 try 外;`run_case` 的 `_run_once` 整体 try 捕获 → 该次 failed;但 `run_chain:78` 调 `run_assertions` **不在 try 内** → `KeyError` 冒泡 → **500**。同理 `run_chain:82` `response.json()` 非 JSON 响应也 500 | `run_chain` 未像 `run_case` 那样包裹断言/取值异常 | 用例设计新发现(关联 BUG-009) | 待修复 |
| BUG-028 | P2 | `retries` 负数 → `UnboundLocalError` → 500 | schema `retries: int\|None=0` 无 `ge=0`;传 `retries=-1` → `_run_with_retry` `attempts=(-1)+1=0` → `for i in range(0)` 不进循环 → 末尾 `result["attempts"]` 引用未定义 `result` → `UnboundLocalError` → **500**(应 422 或按 0 处理) | schema 无下界校验;`_run_with_retry` 未防 attempts≤0;前端 `retries` 输入 `min="0"`(仅前端拦) | 用例设计新发现 | 待修复 |
