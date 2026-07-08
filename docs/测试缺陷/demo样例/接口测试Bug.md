# demo 样例 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。demo_order 为被测样例(无认证/无项目/无前端页)。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-044 | P2 | spec 模块16 路由写 `/demo-order`,实际代码为 `/demo/orders`;POST 返 200 非 201 | spec 写 `/demo-order`(POST/GET);实际 `demo_order.py` router `prefix="/demo/orders"`,POST 无 `status_code=201`(默认 200)。路由偏差属文档笔误(同 BUG-038/041 家族) | spec 文档笔误;被测样例接口未设 201(可接受,非平台约定) | 用例设计新发现 | 待修(改文档) |
