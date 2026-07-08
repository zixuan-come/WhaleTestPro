# 环境管理 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-029 | P1 | 环境 name/base_url 无长度校验、超长 → 500;base_url 无格式校验 | schema `EnvironmentCreate` `name/base_url: str` 无 `min/max_length`;name>100 / base_url>500 → DB `Data too long` → **500**(应 422);base_url 无 URL 格式校验,可存非法串(执行时拼接产异常) | model `name String(100)` / `base_url String(500)`;前端 Environments.vue 已 trim 拦空但无 `maxlength`、无 URL 格式校验 | 用例设计新发现 | 待修复 |
