# 接口管理 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-025 | P1 | 接口 name/method/url/category 无长度校验、空必填可建 | schema 各字段 `str` 无 `min/max_length`;空 name/method/url 经 API → 201 建成空字段接口;name>100 / method>10 / url>500 / category>50 → DB `Data too long` → **500**(应 422) | model 列宽 `name(100)/method(10)/url(500)/category(50)`,落 DB 才报错;前端 Interfaces.vue 输入框无 `maxlength`(但已拦空 name/url) | 用例设计新发现 | 待修复 |
