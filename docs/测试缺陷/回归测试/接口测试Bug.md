# 回归测试 · 接口测试 Bug

> 来源:`docs/bugs.md` 总表按模块拆分的视图。严重度 P0 阻断 / P1 严重 / P2 一般。

| 编号 | 严重度 | 标题 | 现象 | 根因 | 来源 | 状态 |
|------|--------|------|------|------|------|------|
| BUG-031 | P1 | 接口覆盖率可 >100%(含已删接口的幽灵 id) | `run_regression` 覆盖率 `covered_ids = {c.interface_id for 全部用例}` 未与当前接口列表取交集;用例关联的接口被删后 `interface_id` 仍在,计入 `interface_covered`,而 `interface_total` 只数当前接口 → `covered > total` → 覆盖率 >100%(如 3/2=150%);且指定 `case_ids`/`tag` 子集时覆盖率仍按全项目用例算,与本次 `pass_rate` 范围语义不一致 | `covered_ids` 应与 `all_interfaces` 的 id 取交集;覆盖率口径需明确「项目级 vs 本次运行」 | 用例设计新发现 | 待修复 |
