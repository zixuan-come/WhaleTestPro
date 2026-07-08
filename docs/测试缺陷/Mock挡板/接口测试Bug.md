# Mock 挡板 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-011 | P1 | Mock 仅精确匹配,无路径参数通配 | `/orders/{id}` 命不中 `/orders/123` | `db_match` 用 `Mock.path == path` 硬等 | spec A-6 | 待补 |
| BUG-033 | P1 | 挡板 name/path/method 无长度校验、空必填可建、超长 → 500 | schema `MockCreate` `name/path/method: str` 无 `min/max_length`;空 name/path 经 API → 201(前端 Mocks.vue 已 trim 拦 name/path 空,但 API 层不拦);name>100 / path>255 / method>10 → DB `Data too long` → **500**(应 422) | model 列宽 `name(100)/path(255)/method(10)`,落 DB 才报错;前端无 `maxlength` | 用例设计新发现 | 待修复 |
| BUG-034 | P2 | 命中期健壮性:delay_ms 负数 / status 非法码 → 命中 500;method 大小写敏感、path 需自带前导 `/` | schema `delay_ms: int` 无 `ge=0`:传负数经 API 建成,命中时 `time.sleep(负)` → `ValueError` → **500**;`status: int` 无范围校验:非法码 → `JSONResponse(status_code=非法)` 命中时 Starlette 报错 → 500;`db_match` 用 `Mock.method == method` 大小写敏感,建小写 method 命不中大写请求;`path` 命中查 `"/"+full_path`,建挡板 path 未带前导 `/` 则命不中(关联 BUG-011) | schema 缺 delay_ms/status 范围校验;命中匹配大小写/前缀敏感 | 用例设计新发现 | 待修复 |
