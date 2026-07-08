# 项目管理 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-010 | P1 | 缺 `PUT /projects/{id}` | 项目无法改名/改描述 | 未实现更新接口 | spec A-4 | 待补 |
| BUG-023 | P1 | 项目 name/description 无长度校验、空名可建 | schema `name: str` / `description: str\|None` 无 `min/max_length`;空名经 API → 201 建成空名项目;name >100 → DB `Data too long` → **500**;description >500 → **500**(应 422) | model `name String(100)` / `description String(500)`,落 DB 才报错;前端 Projects.vue 建项目输入框无 `maxlength`(但已 trim 拦空) | 用例设计新发现 | 待修复 |
| BUG-024 | P1 | 删除挂有子资源的项目 → 500;删默认项目致孤儿 | 删一个仍挂着接口/用例的项目 → FK 约束(MySQL 1451)→ `IntegrityError`,delete 路由未捕获 → 500(应先校验/级联/软删并给清晰提示);删内置默认项目 id=1 会让迁移老数据变孤儿 | `interface.project_id` FK 无级联;`db_delete` 直接 `db.delete+commit` 无子资源检查;delete 路由缺 `IntegrityError` 处理 | 用例设计新发现 | 待修复 |
