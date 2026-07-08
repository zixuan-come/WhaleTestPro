# 定时调度 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-015 | P1 | 非法 cron → 500,且留孤儿行/状态不一致 | `_parse_cron` 用 `cron.split()` 硬拆 5 段,非标准段数 → 解包 `ValueError` → 500(应 422);段数够但值越界(如 `99 2 * * *`)→ celery `crontab()` 也 `ValueError` → 500。**更深**:`s_create` 先 `db_create`(commit 落库)再 `sync_schedule`,故非法 cron 时 **DB 行已建成、RedBeat 未注册** → 返 500 但库里留孤儿行;`enabled=False` 时 `sync_schedule` 早返回**不解析** → 非法 cron 可静默建成(埋雷),之后 PUT 翻 `enabled=True` 才 500 | `_parse_cron` 未校验段数/取值;service 落库与同步非原子、无回滚 | spec A-3 边界 | 待修复 |
| BUG-035 | P1 | 调度 name/cron/tag 无长度校验、空名可建、超长 → 500 | schema `ScheduleCreate` `name/cron: str`、`tag: str\|None` 无 `min/max_length`;空 name 经 API → 201(前端 Schedules.vue 已 trim 拦空 name/cron,但 API 层不拦);name>100 / cron>100 / tag>50 → DB `Data too long` → **500**(应 422) | model 列宽 `name(100)/cron(100)/tag(50)`,落 DB 才报错;前端无 `maxlength` | 用例设计新发现 | 待修复 |
