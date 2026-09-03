# PR 代码级审查报告：上游堆叠链 #2/#5/#6/#8

- 审查日期: 2026-09-02
- 审查对象: asipp-neutronics/h2iso 的 4 个堆叠 PR（#2 ⊂ #5 ⊂ #6 ⊂ #8，最终态 = PR8 @ 1f30492）
- 审查方法: deep-reviewer mode=deep 逐函数语义审查 + 编排者独立复核（AST / 模块树 / 数值核验）
- 前置: 集成预演（#3208）已完成，integration/wang2022 @ 6979a4d 全量测试 512 passed

## 审查结论

**判定: 修复后合并（Fix-then-merge）**。已在 GitHub 提交 review：
- PR #8: CHANGES_REQUESTED（review id 5085811030）
- PR #6: CHANGES_REQUESTED（review id 5085813345）
- PR #5: COMMENTED（review id 5085815630）
- PR #2: COMMENTED（review id 5085815188）

## 必改项（2 项，均已发回作者）

### 1. modelica_0d.py 370 行不可达死代码
- 位置: `generate_iss_adapters_mo()` L667 主路径 return 之后，L675 第二个 return 起至 L1043 共 369 行不可达（AST 证实函数内 2 个 return）
- 漂移实证: 死代码 L930 `0.25 * n_tot * MW[4]` vs 活代码 L544 `0.25 * n_T * MW[4]`，同一物理量相差 2 倍（n_tot=2·n_T），死拷贝 D2 原子数翻倍违反质量守恒
- 处置: 要求删除 L675-1043 整段

### 2. generate_overrides.py import 指向不存在的模块
- 位置: tests/modelica/generate_overrides.py:39-40
- 问题: `h2iso.io.flowsheet_io` 与 `h2iso.solver.sequential` 在仓库中不存在（编排者以 find src/h2iso 全量模块树复核确认），正确为 `h2iso.flowsheet.schema` / `h2iso.flowsheet.solver`
- 影响: `--solve` 路径一运行即 ModuleNotFoundError

## 应改项（验证诚信，PR #6）

### 3. 基准断言选择性（4 列只断言 1 列）
| 列 | 文献值 | h2iso | 偏差 | 断言 |
|----|--------|-------|------|------|
| CD1 | 4.8647 | 2.5465 | -47.7% | ❌ |
| CD2 | 1.4392 | 2.4128 | +67.6% | ❌ |
| CD3 | 19.9666 | 18.34 | -8.1% | ✅ 唯一被断言 |
| CD4 | 0.0533 | 0.0056 | -89.4% | ❌ |

"11.46% 全局偏差"为误差抵消下的聚合吻合；要求逐列补断言或 xfail+KNOWN_ISSUES。

### 4. 断言口径矛盾
test_cd3_inventory_accuracy docstring 称 "dev < 10%"，断言为 15%。

### 5. ISS-O 单列覆盖不足
标准工况 CD1 偏差 4600× 未进入测试。

## 建议项（不阻塞）

- a_H=0.99/a_T=0.01、Fraction_D_to_SDS=0.001 无溯源
- Fraction_D_to_SDS/T 声明后未被任何方程引用
- 5D adapter He/Imp 结构性丢弃未文档化
- Equilibrator 统计分布（K=4）无温度修正声明
- "5000h 仿真"声明仅存在于手写 REPORT.md，无仓库内可复现路径
- evaluate_flowsheet_inventory cfg=None 静默回退
- casadi 测试缺 slow marker / importorskip

## 复核记录（用户质疑后的独立复核）

1. 370 行死代码: AST 证实 2 return（L667/L675），L675-1043 不可达；漂移证据 L544 vs L930 已核对。成立。
2. h2iso 模块: find src/h2iso 全量模块树无 io/ 与 solver/ 目录；import 错误属实，非审查误报。
3. 断言口径: 用户判定影响不大，轻量修复；选择性断言问题已按用户要求与口径一并列入 review。

## 对 #3209 的影响

#3209（合并推送）阻塞于上游修订。等待 couuas 响应 review 后：
1. 重新 fetch 复核各 PR 新 head
2. 重新执行集成预演（修订版 PR8 与 integration/wang2022 的 delta）
3. 全量测试 + 重新审查
4. 通过后按 #2→#5→#6→#8 顺序合并

本报告为审查档案，随 .github/reviews/ 管理。
