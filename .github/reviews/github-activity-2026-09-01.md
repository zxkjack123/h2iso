# Repository Review: h2iso（项目整体情况 + GitHub 协作活动概览）

- 审阅日期: 2026-09-01
- 审阅范围: 全仓库概览 + GitHub 远端协作活动（PR/issue/comment）
- 审阅深度: 概览级（Overview scan），未执行 Stage ⑤ 双模式深度 bug hunt

## Executive Summary

- Findings: 2 🔴 / 3 🟡 / 2 🟢
- Project Profile: Python 3.9+ 科学计算包（numpy/scipy + CasADi 可选），氢同位素低温精馏 VLE/MESH 求解器。两个仓库（个人仓与组织仓）均为 private。
- Overall Health: **源码层面健康**。TODO/FIXME 为零，架构分层清晰（L1 VLE → L2 MESH → flowsheet → codegen），前一轮 review（`.github/reviews/full-repo-2025-05-19.md`，4🔴/11🟡/3🟢）已由 Phase 3 remediation 计划关闭 11/12 项。**协作与仓库卫生层面存在两类明确风险**：本地约 3.5 个月（2026-05-20 至今）的开发工作全部未提交，与上游 4 个待审 PR 内容重叠。上游 PR 无任何 CI 检查、无任何 review comment。

## ① Repository Overview

### 本地仓库状态

| 项 | 状态 |
|----|------|
| 本地 HEAD | `eba4530` (2026-05-20) |
| 与 `asipp/main`、`origin/main` 分叉 | 0/0（完全一致，无本地未推送 commit） |
| 工作树 | **42 个已修改文件（+1172/-412）+ 约 20 个未跟踪新文件** |
| 2026-08-01 以来提交 | 0 个 |
| TODO/FIXME/HACK/XXX | 0 处（src/ 全扫描） |
| 开发环境 `.venv` | **损坏**：`.venv/bin/python3 → python → /usr/bin/python` 三层 broken symlink（系统实为 `/usr/bin/python3.12`），本地无法运行 pytest |

未提交/未跟踪的关键内容（工作树领先远端的部分）：
- 新模块: `src/h2iso/parity/`（DWSIM 对标）、`src/h2iso/uq/`（不确定性传播）、`src/h2iso/vle/peng_robinson.py`
- 新 fixtures: `tests/fixtures/wang2022/iss_i.json`、`iss_i_aspen_baseline.json`
- 新计划: `.github/plans/dwsim_parity_plan.md`、`engineering-reliability-plan.md`、`iss_i_flowsheet_plan.md`
- 大量 src 修改: `mesh/column.py` (+288)、`cli.py` (+133)、`flowsheet/schema.py` (+118) 等 15 个源文件共 +664/-223

### 计划与文档

`.github/plans/` 含 6 个计划 + `phase4/` 目录（iss_i_data_gap、impurities_and_holdup_spec、uq_propagation_plan），Phase 4 工作已规划。`.github/reviews/` 有前一轮 full-repo review 存档。

### GitHub 远端双仓结构

| 仓库 | 角色 | 可见性 | 状态 |
|------|------|--------|------|
| `zxkjack123/h2iso` | 个人开发仓（origin） | private | 1 个已关闭 PR，无 open issue |
| `asipp-neutronics/h2iso` | 组织上游仓（asipp） | private | 4 个 open PR + 4 个 open issue |

## ② GitHub 协作活动明细

### asipp-neutronics/h2iso：4 个 Open PR（全部等待 @zxkjack123 审阅）

| PR | 标题 | 作者 | 分支 | 关联 Issue | 状态 | Reviews | Comments |
|----|------|------|------|-----------|------|---------|----------|
| #2 | fix: Wang 2022 ISS-O 拓扑修正 | @couuas | couuas:main | #1 | open | 0 | 0 |
| #5 | feat: ISS-I 四塔级联基准 | @couuas | feat/wang2022-issi-benchmark | #3 | open | 0 | 0 |
| #6 | feat: 6 分区氚滞留量模块 | @couuas | feat/wang2022-inventory-benchmark | #4 | open | 0 | 0 |
| #8 | feat: Modelica 0-D 降阶代码生成 | @couuas | feat/modelica-0d-surrogate-integration | #7 | open | 0 | 0 |

关键事实：
- **零协作反馈**：4 个 PR 的 review 数、review comment 数、issue comment 数全部为 0。`requested_reviewers` 均指向 @zxkjack123，即审阅请求已发出但尚未有任何审阅动作。
- **零 CI**：全部 PR 的 combined status 为 `pending`，statuses 为空数组。组织仓对这些 fork PR 未跑任何 CI 检查，PR 正文中宣称的测试结果（如 PR #6 "30 passed in 985s"、PR #2 "残差 2.56×10⁻⁶"）在远端不可验证。
- **链式依赖**：PR #2 修正的 ISS-O fixture 是后续 PR 的基础，#5 的 `ColumnConfig` 几何扩展被 #6 使用，#6 又被 #8 依赖。四个 PR 基于同一 base `eba4530`，合并顺序应为 #2 → #5 → #6 → #8，否则会产生冲突。

### asipp-neutronics/h2iso：4 个 Open Issue（@couuas 自开自派）

| Issue | 类型 | 标题 | Assignee |
|-------|------|------|----------|
| #1 | Bug | wang2022_isso 循环流连接错误导致尾气漏氚 2785 ppm | couuas |
| #3 | Feature | ISS-I 四塔级联基准 + 多平衡器解析 | （未派） |
| #4 | Feature | 逐板 6 分区氚滞留量模块 | （未派） |
| #7 | Feature | Modelica 0-D 降阶代码生成器 | （未派） |

其中 #4 正文的验收标准已全部勾选完成，但 issue 保持 open，未由 PR #6 的 `Closes #4` 自动关闭（PR 未合并）。

### zxkjack123/h2iso：个人仓

- PR #1（Phase 3+ remediation，2026-05-19 开，2026-05-22 关）：`closed` 且 `merged_at=null`，属自关闭快照 PR（commit 直接推 main），0 comments。其声明 "345 passed, 1 skipped" 与本地 `eba4530` 提交历史一致。
- 无 open issue、无 open PR。

### Comment 活动总结

**两个仓库的所有 PR 和 issue 上，issue comment 与 review comment 均为零。** 协作模式为：@couuas 单方向通过 issue→PR 提交工作并请求审阅，@zxkjack123（维护者）尚未在 GitHub 上留下任何回应痕迹。本地工作树中的未提交改动与 @couuas 的 PR 触及相同文件（`flowsheet/solver.py`、`tests/test_flowsheet/test_issi_full.py`、wang2022 fixtures），说明双方在从同一 base 并行开发。

## ③ Incomplete Tasks

| ID | Type | Location | Description | MODIFY_SPEC |
|----|------|----------|-------------|-------------|
| IT-01 | 🔴 uncommitted_work | 本地工作树 | 42 修改文件 + ~20 未跟踪新文件（parity/uq/peng_robinson/iss_i），约 3.5 个月工作未提交，存在丢失风险 | （流程动作：git 提交，非代码编辑） |
| IT-02 | 🔴 pending_review | asipp 4 个 PR | 4 个上游 PR 无 CI、无 review，阻塞合并 | （流程动作：人工审阅 + 启用 CI） |
| IT-03 | 🟡 blocked_external | phase4/iss_i_data_gap.md | ISS-I 工艺数据等待张世坤补齐（Phase 3 遗留 Task 5.1） | |
| IT-04 | 🟢 planned_work | phase4/*.md | 杂质扩展、塔板效率/holdup 导出、UQ 传播、方法论文均已规划 | |

## ④ Potential Bugs / 风险发现

| ID | Severity | Location | Category | Description | Remediation | MODIFY_SPEC |
|----|----------|----------|----------|-------------|-------------|-------------|
| PB-01 | 🔴 | 本地工作树 ↔ 上游 PR | 合并冲突 | 本地未提交的 `flowsheet/solver.py`/`test_issi_full.py`/fixtures 修改与 PR #2/#5 内容重叠；上游 PR 一旦合并并 pull，本地 3.5 个月未提交工作将面临冲突或丢失 | ① 先提交本地工作（分主题成多个 commit）；② 建立与 couuas 的分工确认（本地 iss_i vs 上游 issi 是否重复）；③ 合并 PR 前 stash/commit 本地状态 | |
| PB-02 | 🔴 | asipp 组织仓 | CI 缺失 | 4 个 PR combined status 全为 pending/0 checks。PR 宣称的数值验证（质量守恒误差、滞留量偏差 11.46% 等）无远端证据；`ci.yml` 存在于仓库但未对 fork PR 生效 | 在组织仓启用 GitHub Actions 对 fork PR 的 workflow（或 push 分支至组织仓再提 PR），让每 PR 有可验证的 test/lint 门禁 | |
| PB-03 | 🟡 | 本地 `.venv` | 环境损坏 | venv broken symlink，本地无法运行 pytest/ruff，无法复现 PR 中的测试声明 | 重建 venv：`python3.12 -m venv .venv && pip install -e ".[dev,solver]"` | |
| PB-04 | 🟡 | 上游 issue #4 | 状态不同步 | issue #4 验收项全勾选但 open；`Closes` 关键字因 PR 未合并未生效，任务状态与事实脱节 | 合并 PR 后确认自动关闭，或手动关闭 | |
| PB-05 | 🟢 | 双仓 remote 策略 | 流程 | 个人仓 PR #1 自关闭未走 merge 流程（merged_at=null），历史语义不清 | 单作者快照 PR 可直接 `git push` + tag，无需 PR 仪式 | |

## ⑤ Optimization Opportunities

| ID | Severity | Location | Category | Description | Remediation | MODIFY_SPEC |
|----|----------|----------|----------|-------------|-------------|-------------|
| OP-01 | 🟢 | 协作流程 | 效率 | 4 个 PR 链式依赖却独立提交，审阅顺序不明确 | 在 PR #2 合并前，将 #5/#6/#8 标记为 stacked/dependent；或在 PR 描述中标注 merge order | |
| OP-02 | 🟢 | GitHub | 可见性 | issue/PR 无 label、无 milestone，外部贡献者难以导航 | 添加 labels（bug/feat/wang2022-benchmark 等）与 milestone（Phase 4） | |
| OP-03 | 🟢 | 本地 | 可复现性 | 未跟踪的新 fixtures（iss_i.json、iss_i_aspen_baseline.json）与 plan 文件未纳入版本控制 | 随本地提交一并 git add | |

## Remediation Roadmap

### Priority 1 — 🔴 Critical
1. **PB-01 / IT-01: 提交本地 3.5 个月工作**（影响面：全部未提交成果，成本：medium，阻塞性：阻塞一切后续合并）
   - 分主题提交：parity/ → uq/ → peng_robinson → iss_i fixtures → 其余 src 修改
   - 提交前与 @couuas 确认工作边界，避免与 PR #2/#5 重复实现
2. **PB-02 / IT-02: 处理 4 个待审 PR**
   - 在组织仓启用 CI（或改为 push 组织仓分支提 PR）
   - 按 #2 → #5 → #6 → #8 顺序审阅合并
   - 审阅关注点建议（基于 PR 自述）：PR #2 声称的基准通过数 19/29 中未通过的 10 项是什么。PR #6 滞留量偏差 11.46% 接近文献 10-15% 不确定度上界。PR #8 的 0-D 降阶模型保真度验证口径待确认。

### Priority 2 — 🟡 Warning
3. **PB-03: 重建 .venv**（成本: low；阻塞本地一切测试）
4. **PB-04: 同步 issue 状态**

### Priority 3 — 🟢 Enhancement
5. OP-01~OP-03 流程优化（labels、merge order 标注、文件入版本控制）

## Next Steps

- 本次为概览级审阅，未执行 Stage ⑤ 深度 bug hunt。若需要，可对未提交的本地新模块（`parity/`、`uq/`、`peng_robinson.py`）以及 PR #2/#5/#6/#8 的 diff 做专项深度审阅。
- 对 Priority 1 项，建议委派 @Plan Architect 基于本报告生成可执行的分阶段计划（MODIFY_SPEC 大多留空，因为主要动作是 git/审阅流程而非代码编辑）。

## Limitations

- 未扫描范围：`docs/` 全文、`benchmark/`、`uq_runs/`、`script/` 目录内容；未运行测试套件（.venv 损坏）；未对 4 个 PR 的 diff 逐文件审阅。
- 全部 GitHub 数据来自 API 实查（2026-09-01），本地状态来自 git 实查。PR 正文中的数值声明（ppm、mol/h、% 等）为转述，未经独立数值验证。
- 本报告为内部工件，未执行完整 de-ai-fier 术语/单位门禁（L1-Tone 档）。

## Pre-Delivery Audit (L1-Lite)

| 检查项 | 结果 | 依据 |
|--------|------|------|
| 定量声明与工具输出一致 | ✅ PASS | 42 修改文件/+1172/-412 来自 `git diff --stat`；4 PR/4 issue/0 comment 来自 github MCP 返回；0/0 分叉来自 `git rev-list --left-right --count` |
| 无编造 GitHub 实体 | ✅ PASS | 全部 PR/issue 编号、作者、时间戳与 API 返回逐项核对 |
| 不确定项标注 | ✅ PASS | PR 正文数值声明已标注"转述未经独立验证"；本地工作归属推断标注为需要确认 |
| 无破坏性操作 | ✅ PASS | 全程只读，仅创建 `.github/reviews/github-activity-2026-09-01.md` |

## Doublecheck Spot-check（机查复验）

委派 Doublecheck 对 6 组关键定量声明独立实查（GitHub API + 本地 git），结果 **6/6 PASS，0 FAIL**：

| # | 声明 | 判定 |
|---|------|------|
| 1 | asipp 4 个 open PR（#2/#5/#6/#8）作者 couuas、reviewers=zxkjack123、reviews/comments 全 0 | ✅ PASS |
| 2 | asipp 4 个 open issue（#1/#3/#4/#7）comments 全 0 | ✅ PASS |
| 3 | zxkjack123 仅 1 个 closed PR #1（merged_at=null） | ✅ PASS |
| 4 | 本地 HEAD eba4530，与两 remote 分叉 0/0 | ✅ PASS |
| 5 | 本地 42 修改文件 +1172/-412，8 月以来 0 提交 | ✅ PASS |
| 6 | 4 个上游 PR combined status 均 pending/0 statuses | ✅ PASS |

备注：Doublecheck 指出 GitHub `list_issues` 接口会把 PR 混入 issue 列表（返回 8 条），本报告已按纯 issue 口径（#1/#3/#4/#7）表述，不受影响。

## 知识产权候选清单（IP Protection Gate 1.5）

- **T6 命中**：PR #1 自述"public preprint"计划，仓库处于公开前窗口期。建议公开前委派 @IP Protection Advisor 做 M5 portfolio sweep。
- **T2 候选（稳定可复用算法/模块）**：
  - `src/h2iso/vle/`（Souers 蒸汽压 + 氚量子修正、SRK EOS 锚定）
  - `src/h2iso/mesh/`（CasADi MESH 稳态求解 + continuation 温启动）
  - `src/h2iso/inventory/`（PR #6，逐板 6 分区气液滞留量积分）
  - `src/h2iso/codegen/modelica_0d.py`（PR #8，0-D 物理降阶 Modelica 代码生成）
  - 本地未提交的 `src/h2iso/parity/`、`src/h2iso/uq/`
- **风险提示**：① 开源前确认参数数据（Souers 系数、BIP、Wang 2022 基准数据）的公开来源属性；② 双仓（个人 zxkjack123 + 组织 asipp-neutronics）归属与署名口径需在开源时统一；③ 0-D 降阶方法论若属新提出（PR #8），与论文发表顺序的协调需注意新颖性窗口。
