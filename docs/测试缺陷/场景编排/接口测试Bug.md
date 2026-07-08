# 场景编排 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-030 | P1 | 场景 name/description 无长度校验、空名可建、超长 → 500;前端编辑区空名静默兜底 | schema `ScenarioCreate` `name/description: str` 无 `min/max_length`;空 name 经 API → 201;name>100 / description>500 → DB `Data too long` → **500**(应 422);前端新建弹窗拦空名,但编辑区 `saveCurrent` 空名兜底 `'未命名'`(不拦、静默改,两处不一致) | model `name String(100)` / `description String(500)`,落 DB 才报错;前端 Orchestration.vue 无 `maxlength` | 用例设计新发现 | 待修复 |
