# 登录注册 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-013 | P0 | 账号长度未按需求 4–20 校验 | 需求账号 4–20 位,但 <4、(20,50] 均被接受注册(应 422);>50 触发 DB `Data too long`→**500**;含空账号 | 前端 Login.vue 输入框无 `minlength/maxlength`;后端 schema `username: str` 无 `min/max_length`,落 DB `String(50)` 才报错 | 用例设计新发现 | 待修复 |
| BUG-014 | P1 | 密码长度缺少边界校验 | 原规则为 8–20 位；2026-09-18 产品口径调整为 4–20 位，空、<4、>20 均应返回 422 | 前后端曾缺少一致的密码长度校验 | 用例设计新发现 | 已修复（现行规则 4–20 位） |
| BUG-019 | P2 | `/auth/register` 创建成功返回 200,偏离 201 约定 | 其余 8 个创建接口(case/environment/perf/interface/mock/project/scenario/schedule)均显式 `status_code=201`,唯 register 未设 → 默认 200 | router 该行缺 `status_code=201` 参数 | 用例设计新发现 | 待修复 |
| BUG-022 | P0 | 并发同名注册 → 500 | 高并发下两请求同时过 `s_register` 的「预查不存在」判断,随后双双 INSERT,第二条命中 `username` 唯一约束 → `IntegrityError` 未被捕获 → 500(应 400「用户名已存在」) | `s_register` 是 check-then-insert 非原子;`users.username unique=True`;service 未 try 捕获 `IntegrityError` 转 400 | 用例设计新发现 | 待修复 |
