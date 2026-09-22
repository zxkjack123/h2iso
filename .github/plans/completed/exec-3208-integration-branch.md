# 执行计划：PM #3208 — h2iso 集成分支预演（6 文件冲突一次性解决）

> **plan**: exec-3208-integration-branch | **task**: PM #3208（TRITIUM-CYCLE, status=doing, assignee=张小康, 依赖 #3207 done）
> **repo**: /home/gw/opt/h2iso | **scope_mode**: HOLD（预演/修复类，严格 6 文件边界，不扩展）
> **generated_at**: 2026-09-02 | **git_commit**: d7223f5bada9cb5f9df010b636edfa3e3aa1674d
> **plan sha256**: 执行前（T0.1 阶段，任何回写前）`sha256sum .github/plans/exec-3208-integration-branch.md` 重测一次并记录
> **上游决策 oracle**: .github/reviews/local-commit-plan-2026-09-01.md 第三节"冲突文件性质预判表" + Phase C 决策原则

## 授权归因（三要素）

- ① 授权主体：张小康（PM #3208 assignee，本计划为其执行而产出）
- ② 时点与载体：PM 系统 task #3208（status=doing，依赖 #3207 已完成；notes 已载明执行内容与验收标准）
- ③ 授权范围：**仅** 本计划 Phase A–D（integration/wang2022 分支预演 + 6 文件冲突解决 + commit 记录）。明确排除：修改 main、push 任何远端、在 GitHub 上合并 PR（属于 #3209）。**不含任何 D2 门控的预先批准**——计划中一切 STOP 项均须经用户当场确认（NEEDS_USER_DECISION）。

## 任务概述

上游 asipp-neutronics/h2iso 有堆叠 PR 链 pr/2 ⊂ pr/5 ⊂ pr/6 ⊂ pr/8（`refs/remotes/asipp/pr/N`，已 fetch）。本地 main（d7223f5）与 pr/8 的冲突面为 6 个文件。本任务在 `integration/wang2022` 分支上做一次性 merge 预演：解决全部冲突、全量 pytest 验证、commit 记录解决方案、分支保留存档。**不触碰 main、不 push、不合并 GitHub PR。**

### 冲突面精确图（已用只读 merge-tree 预演实测，执行时复核）

`git merge-tree --write-tree HEAD refs/remotes/asipp/pr/8` 实测（2026-09-02）：

| 文件 | 冲突类型 | 解决动作 |
|------|---------|----------|
| `src/h2iso/flowsheet/solver.py` | 文本冲突 ×1 hunk（`_resolve_stream` equilibrator 输出块） | 四段语义叠加（PR 快路径 + 本地精确回退 + PR legacy + 本地 backward-compat） |
| `src/h2iso/flowsheet/schema.py` | 文本冲突 ×2 hunk（ColumnConfig 字段块 + 构造调用块） | 双字段族保留（本地 eos/splitter + PR 几何字段族） |
| `tests/test_flowsheet/test_isso_no_recycle.py` | 文本冲突 ×2 处（comprehension filter 行） | PR 拓扑值 `CD2_top` + 本地格式 |
| `tests/test_flowsheet/test_sweep.py` | 文本冲突 ×3 处（同上模式） | 同上 |
| `tests/test_flowsheet/test_isso_full.py` | **自动合并**（双侧 hunk 不重叠，已验证组合 blob 无冲突标记） | 不改动，仅验证 |
| `tests/test_flowsheet/test_schema.py` | **自动合并**（同上） | 不改动，仅验证 |

⚠️ 精化说明：源计划称"6 文件冲突"，实测为 **4 文件需手工解决 + 2 文件自动合并仅验证**。二者不矛盾——6 文件均为"双侧修改面"，全部纳入本计划显式处理，自动合并文件若实测出现冲突标记即视为预演失效（T2.6 STOP 条件）。

### 关键残余风险（预演的目的正是暴露它）

PR8 同时修改了 `tests/fixtures/wang2022/wang2022_isso.json`（拓扑修复：`CD2_bottom_recycle` → `CD2_top`，PR 侧干净带入，本地未改该文件）。本地侧以下**不在 6 文件范围内**的测试/代码运行时面对新 fixture，行为不可预判：`tests/test_flowsheet/test_cli_flowsheet.py`、`tests/test_uq/test_isso_uq.py`（+`src/h2iso/uq/run_isso.py`、`src/h2iso/parity/h2iso_runner.py`）。若 C2 全量测试在它们身上失败 → 属 6 文件外，**不得擅自修改**，走 D2 STOP。

## 假设清单（CoT Stage 2）

1. `[假设: 上游 PR 链在预演执行期间不变化]` — 高影响若错 → D1 SHA 复核兜底（漂移即 STOP）。
2. `[假设: main@d7223f5 全量 pytest 基线为绿]` — 仅 smoke 验证过 test_schema.py（12 passed），未全量实测 → 提供 T0.2 可选基线快照；若基线本身有红，T3.3 分诊须区分"既有红"与"集成引入红"。
3. `[假设: 全量 pytest 时长 < 40 分钟]` — 中影响 → 命令带显式 timeout。
4. `[假设: 实际 merge 冲突 hunk 与本次 merge-tree 预演一致]` — 高影响 → T2.1 用 `--diff-filter=U` 现场复核。
5. `[假设: 执行器具备 bash/git 写权限且全程遵守 .venv 约束]` — 低影响。

## 全局执行约束（违反即失败）

- 只允许 `.venv/bin/python`（含 `-m pytest`、`-m ruff`）与 `.venv/bin/pip`；本计划不含任何 pip 操作。
- **排除项（永不进入 staging/commit）**：`.github/plans/exec-3207-local-commit.md`、`.github/plans/exec-3208-integration-branch.md`（本文件）。禁止 `git add -A` / `git add .` / `git stash -u`。
- merge 进行中（MERGE_HEAD 存在）**禁止任何 `git checkout`**；回滚只允许 `git merge --abort`。
- 不触碰 main（不 checkout、不 commit、不 push）；预演全程在 integration/wang2022 上进行。

---

## Phase 0：基线固化（T0）

> 每 Phase 首步为基线漂移重检：所有 SHA/状态均在执行时实测，不沿用本文件生成时快照。

#### Task T0.1: 基线固化与工作树确认
- **目标**：把执行前状态固化为可对照的基线
- **依赖**：无 | **frontier**：是
- **执行者**：task-executor
- **修改内容**：无（只读）
- **修改边界**：禁止任何写操作（无 fetch、无 checkout、无 branch）
- **质量检查方式**：逐条命令核对输出
- **验收标准**：
  - ✅ `git rev-parse HEAD` 输出 `d7223f5bada9cb5f9df010b636edfa3e3aa1674d`
  - ✅ `git branch --show-current` 输出 `main`
  - ✅ `git status --porcelain=v1` 输出恰为以下两行（顺序可异，不得有其他行）：
    ```
    ?? .github/plans/exec-3207-local-commit.md
    ?? .github/plans/exec-3208-integration-branch.md
    ```
  - ✅ `git rev-parse refs/remotes/asipp/pr/8` 输出 `1f30492cc5a17410bf48dbd96dc445b791a3d597`
- **潜在风险**：工作树若有未预期脏文件（如编辑器临时文件）→ 停下，先与用户确认再继续
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T0.2: 基线全量 pytest 快照（可选，best-effort）
- **目标**：记录 main@d7223f5 的测试基线，供 T3.3 分诊对照
- **依赖**：T0.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：无（只读测试运行）
- **修改边界**：不得修改任何文件修复基线失败——基线失败只记录不修复
- **质量检查方式**：记录 exit code + failed 清单
- **验收标准**：
  - ✅ 命令执行完毕并记录结果摘要（通过 OR 失败清单 OR 超时放弃均视为完成）
  - ✅ 命令：`set -o pipefail; timeout 2400 .venv/bin/python -m pytest tests/ -q --tb=line 2>&1 | tail -30`（addopts 自动排除 benchmark/e2e；pipefail 确保 pytest 失败/超时 exit 124 不被 tail 掩盖）
- **潜在风险**：运行期间工作树/分支保持不变（pytest 不写仓库文件）；h2iso_results.json 若被测试写入 repo 根 → 属 untracked 新文件，后续 Phase 的 status 检查需将其加入排除说明（若出现）
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

---

## Phase A：预检（D1 门控）

#### Task T1.1: fetch 与 PR ref SHA 复核
- **目标**：更新远端 ref 并复核 pr/8 未漂移
- **依赖**：T0.1 | **frontier**：是（T0.1 完成后首个写操作）
- **执行者**：task-executor
- **修改内容**：`git fetch asipp`（更新 refs/remotes/asipp/*，不触碰工作树与本地分支）
- **修改边界**：不得 fetch origin、不得 pull/merge/rebase 任何本地分支
- **质量检查方式**：逐条核对 SHA
- **验收标准**：
  - ✅ `git rev-parse refs/remotes/asipp/pr/8` == `1f30492cc5a17410bf48dbd96dc445b791a3d597`
  - ✅ `git rev-parse refs/remotes/asipp/pr/2` == `6d79258bededbbd478c46f36f834dc29d14fd5d7`
  - ✅ `git rev-parse refs/remotes/asipp/pr/5` == `fd7ddab3444ba9534eae3b5f7f33606377f11387`
  - ✅ `git rev-parse refs/remotes/asipp/pr/6` == `8e6610672fe18b169a387b109f174ac7ca6c8e68`
  - ⛔ **任一不符 → STOP + NEEDS_USER_DECISION**（附实测 SHA + `git log --oneline <旧SHA>..<实测SHA>` 漂移提交清单）
- **潜在风险**：fetch 期间上游 couuas 恰有 push → 正是本检查要捕获的场景
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T1.2: merge-base 与冲突清单复核
- **目标**：确认堆叠链与冲突面与预演一致（只读，`git merge-tree` 不修改任何状态）
- **依赖**：T1.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：无（只读）
- **修改边界**：无
- **质量检查方式**：输出逐条对照
- **验收标准**：
  - ✅ `git merge-base HEAD refs/remotes/asipp/pr/8` == `eba4530ae28b8b63cf483a17274d5cebc58b2c19`
  - ✅ `git merge-base --is-ancestor refs/remotes/asipp/pr/2 refs/remotes/asipp/pr/5`、pr/5→pr/6、pr/6→pr/8 三条均 exit 0
  - ✅ `git merge-tree --write-tree HEAD refs/remotes/asipp/pr/8` 的 CONFLICT 文件清单**恰为** 4 文件：`src/h2iso/flowsheet/schema.py`、`src/h2iso/flowsheet/solver.py`、`tests/test_flowsheet/test_isso_no_recycle.py`、`tests/test_flowsheet/test_sweep.py`
  - ⛔ **冲突清单不一致（多出或缺失文件）→ STOP + NEEDS_USER_DECISION**（冲突面漂移，本计划决策原则不覆盖新文件）
- **潜在风险**：merge-tree 输出格式随 git 版本变化 → 判读以 `CONFLICT (content): Merge conflict in <path>` 行集合为准
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T1.3: 分支存在性与工作树复核 → **D1 门控**
- **目标**：确认 integration/wang2022 不存在、工作树状态与 Phase 0 一致
- **依赖**：T1.2 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：无（只读）
- **修改边界**：无
- **质量检查方式**：输出逐条对照
- **验收标准**：
  - ✅ `git branch --list integration/wang2022` 输出为空
  - ✅ `git status --porcelain=v1` 与 T0.1 基线一致（仅两个 untracked plan 文件；若 T0.2 产生了 h2iso_results.json 等新 untracked 文件，须在此登记为排除项并延续到全部后续检查）
  - ✅ `git rev-parse main` == `d7223f5...`（main 未被任何操作移动）
- **潜在风险**：若存在同名遗留分支 → STOP + NEEDS_USER_DECISION（判断是否可安全删除）
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

**D1 门控判定**：T1.1–T1.3 验收标准全部满足 → 进入 Phase B。任一 ⛔ STOP 项触发 → 停止执行，向用户呈报 `NEEDS_USER_DECISION`（含触发项、实测值、建议选项），等待用户决定后继续。

---

## Phase B：建分支 + merge + 冲突解决

#### Task T2.1: 建分支 + `merge --no-commit`
- **目标**：从 main@d7223f5 建 integration/wang2022 并启动无提交 merge
- **依赖**：D1 通过 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：创建分支 + 索引进入 merge 状态（工作树写入冲突标记）
- **修改边界**：禁止 `--squash`/`--no-ff` 之外的变体；必须用 `--no-commit`；merge 目标必须是 `refs/remotes/asipp/pr/8`
- **质量检查方式**：命令序列照抄，逐步核对
- **验收标准**：
  - ✅ `git checkout -b integration/wang2022 main` 成功，`git branch --show-current` == `integration/wang2022`
  - ✅ `git merge --no-commit refs/remotes/asipp/pr/8` 退出并报告 conflict（不 commit）
  - ✅ `git diff --name-only --diff-filter=U` 输出**恰为** 4 个文本冲突文件（schema/solver/test_isso_no_recycle/test_sweep）
  - ⛔ 冲突文件数 != 4 或文件集不符 → 立即 `git merge --abort` → STOP + NEEDS_USER_DECISION
- **潜在风险**：⚠️ 从此处起 MERGE_HEAD 存在——**禁止任何 git checkout**，直到 T4.1 commit 或回滚 abort
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T2.2: 解决 `src/h2iso/flowsheet/schema.py`（2 个冲突 hunk）
- **目标**：双字段族共存——本地 `eos`/`splitter` 字段族 + PR 几何字段族
- **依赖**：T2.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**（仅该文件）：
  - **Hunk 1**（`class ColumnConfig` 字段块）：`pressure: float` 行之后依次保留——本地 `eos: str = "souers"  # "souers" or "peng-robinson"`，随后 PR 的 6 个字段 `pressure_top_Pa: float = 101325.0`、`pressure_bottom_Pa: float = 101325.0`、`inside_diameter_m: float = 0.05`、`HETP_m: float = 0.05`、`condenser_volume_m3: float = 1.0e-3`、`reboiler_volume_m3: float = 2.0e-4`（含各自默认值）
  - **Hunk 2**（`load_flowsheet` 中 ColumnConfig 构造调用）：取本地多行格式，字段全集 = `name, n_stages, reflux_ratio, distillate_to_feed, feed_positions, pressure` + 本地 `eos=cdata.get("eos", "souers")` + PR 的 `pressure_top_Pa=p_top`、`pressure_bottom_Pa=p_bot`、`inside_diameter_m=cdata.get("inside_diameter_m", 0.05)`、`HETP_m=cdata.get("HETP_m", 0.05)`、`condenser_volume_m3=cdata.get("condenser_volume_m3", 1.0e-3)`、`reboiler_volume_m3=cdata.get("reboiler_volume_m3", 2.0e-4)`
  - **不动的部分**（非冲突 hunk，merge 已正确保留，勿动）：`splitter: dict` 字段（FlowsheetConfig）、`splitter=data.get("splitter", {}).get("ratios", {})`、equilibrator 双路径解析（本地版）、所有 cosmetic 重排
- **修改边界**：不得改动该文件其余任何行；不得新增字段或改写字段默认值
- **质量检查方式**：
  - `grep -n 'eos: str = "souers"' src/h2iso/flowsheet/schema.py` 命中 1 处
  - `grep -cn 'inside_diameter_m' src/h2iso/flowsheet/schema.py` == 2（字段声明 + 构造传参）
  - `grep -cn 'HETP_m' src/h2iso/flowsheet/schema.py` == 2
  - `grep -n 'splitter: dict' src/h2iso/flowsheet/schema.py` 命中 1 处
  - `grep -nE '^(<<<<<<<|>>>>>>>|=======)' src/h2iso/flowsheet/schema.py` 无输出
  - `.venv/bin/python -m ruff check src/h2iso/flowsheet/schema.py` exit 0
- **验收标准**：
  - ✅ 上述 6 条检查全过
- **潜在风险**：字段顺序错位导致 dataclass 初始化爆 TypeError → 以 pytest C1 兜底
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T2.3: 解决 `src/h2iso/flowsheet/solver.py`（1 个冲突 hunk，四段叠加）
- **目标**：`_resolve_stream` 的 equilibrator 输出解析 = PR 快路径 + 本地精确回退语义叠加
- **依赖**：T2.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**（仅该文件、仅该 hunk）——合并后自上而下的顺序：
  1. **PR 的 generic 快路径**（置于最前）：
     ```python
     # Check unit generic output (e.g., equilibrator1_out, mixer_out)
     if f"{source_name}_out" in self.streams:
         return self.streams[f"{source_name}_out"]
     ```
  2. **本地的 config.equilibrators 精确匹配**（紧随其后）：保留 `for eq_cfg in self.config.equilibrators:` 循环中 `source_name == eq_name` 与 `source_name == eq_name + "_output"` 两个分支；**丢弃本地循环内冗余的 `if source_name == eq_name: for key...` 死代码块**（其条件与第一分支重复）
  3. **PR 的 legacy fallback 块**：`if "equilibrator" in source_name:` 下的两级扫描（`key.startswith(source_name) and key.endswith("_out")`；再 `"equilibrator" in key and "out" in key`）
  4. **本地的 ISS-O backward-compat 块**（置于末尾）：`source_name in ("equilibrator", "equilibrator_output") and "equilibrator_out" in self.streams` → 返回 `self.streams["equilibrator_out"]`
  - **不动的部分**：`import copy`、`_apply_split` 方法、`eos=col_cfg.eos` 传参、`_get_tear_output` 及其注释、全部 cosmetic 重排（均非冲突 hunk）
- **修改边界**：不得改动该文件其余任何行；不得改变 `_resolve_stream` 其余分支（tear/`{base}_bottoms` 等）顺序
- **质量检查方式**：
  - `grep -n 'f"{source_name}_out" in self.streams' src/h2iso/flowsheet/solver.py` 命中 1 处（PR 快路径）
  - `grep -cn 'self.config.equilibrators' src/h2iso/flowsheet/solver.py` >= 2（本地精确匹配在场）
  - `grep -n 'key.startswith(source_name) and key.endswith("_out")' src/h2iso/flowsheet/solver.py` 命中 1 处（PR legacy）
  - `grep -n '"equilibrator", "equilibrator_output"' src/h2iso/flowsheet/solver.py` 命中 1 处（本地 backward-compat）
  - `grep -nE '^(<<<<<<<|>>>>>>>|=======)' src/h2iso/flowsheet/solver.py` 无输出
  - `.venv/bin/python -m ruff check src/h2iso/flowsheet/solver.py` exit 0；`.venv/bin/python -m py_compile src/h2iso/flowsheet/solver.py` exit 0
- **验收标准**：
  - ✅ 上述 6 条检查全过
- **潜在风险**：四段顺序若颠倒（如 legacy 先于精确匹配）会导致 ISS-I 的 equilibrator1/equilibrator2 解析错误 → 按给定顺序排列，C1 的 test_issi_full.py 兜底
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T2.4: 解决 `tests/test_flowsheet/test_isso_no_recycle.py`（2 处同模式冲突）
- **目标**：PR 拓扑值 + 本地格式——filter 行的元组取 PR 的 `("CD2_top", "CD3_top")`，行排布取本地多行 comprehension 格式
- **依赖**：T2.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**（仅该文件）：2 处冲突 hunk（`config.connections` 与 `col.feed_positions` 各 1 处）均解析为：
  ```python
  config.connections = [
      conn
      for conn in config.connections
      if conn.from_unit not in ("CD2_top", "CD3_top")
  ]
  ```
  （feed_positions 处同构：`k: v` / `for k, v in col.feed_positions.items()` / `if k not in ("CD2_top", "CD3_top")`）
  - 该文件其余部分（FIXTURE_PATH 重排、h2_frac/heavy_frac f-string 断言）已自动合并，勿动
- **修改边界**：不得改动该文件其余任何行
- **质量检查方式**：
  - `grep -c '"CD2_top", "CD3_top"' tests/test_flowsheet/test_isso_no_recycle.py` == 2
  - `grep -c 'CD2_bottom_recycle' tests/test_flowsheet/test_isso_no_recycle.py` == 0
  - `grep -nE '^(<<<<<<<|>>>>>>>|=======)' tests/test_flowsheet/test_isso_no_recycle.py` 无输出
  - `.venv/bin/python -m ruff check tests/test_flowsheet/test_isso_no_recycle.py` exit 0
- **验收标准**：
  - ✅ 上述 4 条检查全过
- **潜在风险**：遗漏 feed_positions 处的第二 hunk → C1 该文件失败兜底
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T2.5: 解决 `tests/test_flowsheet/test_sweep.py`（3 处同模式冲突）
- **目标**：与 T2.4 相同模式（PR 拓扑值 + 本地格式），共 3 处（两个测试类的 setup + export 测试）
- **依赖**：T2.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**（仅该文件）：3 处冲突 hunk 全部解析为本地多行 comprehension 格式 + `("CD2_top", "CD3_top")`
- **修改边界**：不得改动该文件其余任何行（含 FIXTURE_PATH 重排、`R[{i - 1}]` f-string、`import json` 空行分隔——均自动合并，勿动）
- **质量检查方式**：
  - `grep -c '"CD2_top", "CD3_top"' tests/test_flowsheet/test_sweep.py` == 6（实测 PR 侧恰 6 行：3 个冲突 hunk × 每 hunk 2 行 filter——from_unit 与 feed_positions 各一行）
  - `grep -c 'CD2_bottom_recycle' tests/test_flowsheet/test_sweep.py` == 0
  - `grep -nE '^(<<<<<<<|>>>>>>>|=======)' tests/test_flowsheet/test_sweep.py` 无输出
  - `.venv/bin/python -m ruff check tests/test_flowsheet/test_sweep.py` exit 0
- **验收标准**：
  - ✅ 上述 4 条检查全过
- **潜在风险**：3 处 hunk 内容相似易漏改 → 以 grep 计数 ==6 精确验收（3 hunk × 2 行/每 hunk）
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T2.6: 验证 2 个自动合并文件（不改动）
- **目标**：确认 test_isso_full.py 与 test_schema.py 的自动合并结果语义正确（PR 断言数值 + 本地 f-string 消息共存）
- **依赖**：T2.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：无（只读验证；若文件符合预期则保持 git 自动合并结果原样）
- **修改边界**：**不得编辑这两个文件**——任何"顺手修复"都越界
- **质量检查方式**：
  - `grep -n 'rel_error < 0.001' tests/test_flowsheet/test_isso_full.py` 命中 1 处（PR 收紧的质量守恒断言在场）
  - `grep -n 'CD2_top recycles to CD1' tests/test_flowsheet/test_isso_full.py` 命中（PR 注释在场）
  - `grep -n 'f"CD3 bottom heavy isotopes' tests/test_flowsheet/test_isso_full.py` 命中 1 处（本地 f-string 消息在场）
  - `grep -n 'CD2_top -> CD1 and CD3_top -> CD2' tests/test_flowsheet/test_schema.py` 命中（PR docstring 在场）
  - 两文件均 `grep -nE '^(<<<<<<<|>>>>>>>|=======)'` 无输出
- **验收标准**：
  - ✅ 上述检查全过 → 两文件保持自动合并结果
  - ⛔ 任一文件出现冲突标记或关键内容缺失 → STOP + NEEDS_USER_DECISION（实际 merge 行为与预演不符）
- **潜在风险**：git 版本差异导致自动合并行为不同 → 本检查即兜底
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T2.7: 显式 staging + 未合并残留检查
- **目标**：6 文件进入 stage-0，索引无 unmerged 残留，排除项未被卷入
- **依赖**：T2.2–T2.6 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：仅 staging（显式 6 路径）：
  ```bash
  git add src/h2iso/flowsheet/schema.py src/h2iso/flowsheet/solver.py \
          tests/test_flowsheet/test_isso_no_recycle.py tests/test_flowsheet/test_sweep.py \
          tests/test_flowsheet/test_isso_full.py tests/test_flowsheet/test_schema.py
  ```
- **修改边界**：**禁止 `git add -A` / `git add .` / 通配符**；不得 stage 任何 6 文件之外的新修改
- **质量检查方式**：
  - `git ls-files -u` 输出为空（无 unmerged 残留）
  - `git status --porcelain=v1 | grep -E 'exec-3207|exec-3208'` 无输出（两个 plan 文件仍 untracked，未入 staging）
  - `git diff --cached --name-only` 包含上述 6 文件
- **验收标准**：
  - ✅ 上述 3 条检查全过
- **潜在风险**：merge 已将 PR8 全部文件（含自动合并文件与新文件）stage——`git add` 显式 6 路径是幂等补齐，不是覆盖
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

---

## Phase C：集成分支验证

> 背景：PR8 带入的新测试文件（merge 自动 stage）：`tests/test_codegen/test_modelica_0d.py`（纯字符串 codegen，无 OpenModelica 依赖）、`tests/test_inventory/test_column_inventory.py`、`tests/test_inventory/test_wang2022_inventory_benchmark.py`（numpy-based）、`tests/test_flowsheet/test_issi_full.py`（ISS-I 全系统求解，依赖合并后的 solver 解析）。e2e 与 benchmark 由 addopts 自动排除；tests/modelica/*.py 不以 test_ 开头，不被收集。

#### Task T3.1: C1 定向子集验证（冲突解决正确性）
- **目标**：分钟级反馈——6 文件 + 直接依赖合并结果的 PR 新测试
- **依赖**：T2.7 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：无（只读测试运行）
- **修改边界**：失败时不得直接改文件——先走 T3.3 分诊
- **质量检查方式**：记录 exit code 与 failed 清单
- **验收标准**：
  - ✅ `timeout 1200 .venv/bin/python -m pytest tests/test_flowsheet/test_schema.py tests/test_flowsheet/test_isso_no_recycle.py tests/test_flowsheet/test_sweep.py tests/test_flowsheet/test_isso_full.py tests/test_flowsheet/test_issi_full.py tests/test_inventory/ tests/test_codegen/test_modelica_0d.py -q --tb=short` 全绿（exit 0）
  - ⛔ 有失败 → T3.3 分诊（不阻断，先分诊再决定）
- **潜在风险**：ISS-I/ISS-O 全系统用例为 CasADi 求解（分钟级）→ timeout 1200s
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T3.2: C2 全量 pytest
- **目标**：任务级验收——`pytest tests/` 全量通过
- **依赖**：T3.1 通过 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：无
- **修改边界**：失败时不得直接改文件——先走 T3.3 分诊
- **质量检查方式**：记录 exit code 与 failed 清单
- **验收标准**：
  - ✅ `timeout 2400 .venv/bin/python -m pytest tests/ -q --tb=short` 全绿（exit 0；addopts 自动排除 benchmark/e2e）
  - ⛔ 有失败 → T3.3 分诊
- **潜在风险**：见任务概述"关键残余风险"——本地 UQ/parity/CLI 测试对新 fixture 的兼容性是本预演要暴露的核心未知
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T3.3: 失败分诊（**D2 门控**）
- **目标**：把失败归入两类——6 文件内（可修）vs 6 文件外（STOP）
- **依赖**：T3.1/T3.2 任一出现失败时 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：分诊动作如下：
  1. 定位每个失败的文件与测试名（`pytest ... --tb=line` 输出）
  2. **若失败文件 ∈ 6 文件集** → 修复仍严格遵守 Phase B 各文件决策原则 → `git add` 该文件 → 重跑 T3.1（及 T3.2 受影响部分）；修复轮次上限 **2 轮**；第 3 轮仍失败 → STOP + NEEDS_USER_DECISION
   3. **若失败文件 ∉ 6 文件集**（如 test_uq/test_isso_uq.py、test_parity/*、test_cli_flowsheet.py、src/h2iso/uq/*、src/h2iso/parity/*）→ **不修改任何文件** → STOP + NEEDS_USER_DECISION，报告包含：失败文件完整路径、失败测试名、错误摘要、涉及符号、对照 T0.2 基线结论（基线红=既有问题 vs 基线绿=集成引入）、建议选项（A 扩大范围修 / B 接受已知失败继续 commit / C 放弃预演）
   - **例外（分诊粒度澄清）**：`tests/test_flowsheet/test_issi_full.py` 属 PR-only 新文件（∉ 6 文件集），但它是 T3.1 定向子集的验证成员，直接依赖 6 文件解决正确性（T2.3 已明示其兜底四段顺序）。该文件失败时，先按 6 文件根因排查（如 solver.py 快路径顺序、schema.py 字段缺失）并允许在 6 文件集内修复；仅当根因确认在 6 文件之外时才触发 STOP
   4. 对照 T0.2 基线：若同一测试在 main@d7223f5 上也是红 → 标记"既有问题"，不影响本任务判定，仍随报告呈报
   5. **超时分诊分支**：T3.1/T3.2 若 exit 124（timeout）→ 无法执行分诊第 1 步定位失败文件 → 直接 STOP + NEEDS_USER_DECISION（报告含超时命令、耗时上限、最后输出片段、建议选项 A 加长时限 / B 缩小测试范围 / C 放弃预演）
- **修改边界**：分诊过程除"6 文件内修复"外不得写任何文件
- **质量检查方式**：分诊报告完整性（文件/测试/错误/基线对照四要素）
- **验收标准**：
  - ✅ C2 全绿 → D2 通过，进入 Phase D
  - ⛔ 触发 STOP 条件 → 停止并呈报 NEEDS_USER_DECISION
- **潜在风险**：分诊时反复改 6 文件引入新回归 → 轮次上限兜底
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

---

## Phase D：记录解决方案

#### Task T4.1: commit 集成解决方案
- **目标**：以显式 commit message 固化解决方案（不用 `--no-edit` 的 merge 默认消息）
- **依赖**：D2 通过 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：仅 commit（不 push、不 checkout）
- **修改边界**：commit 后停留在 integration/wang2022；禁止 `git checkout main`
- **质量检查方式**：commit 前负向 + 正向核对
- **验收标准**（按序）：
  - ✅ 提交前检查 1（负向）：`git diff --cached --name-only | grep -E 'exec-3207|exec-3208'` 无输出
  - ✅ 提交前检查 2（结构）：`git ls-files -u` 为空；`git status --porcelain=v1` 中两个 plan 文件仍为 `??`
  - ✅ commit 命令（消息单行 + 多行 body，避免内嵌双引号）：
    ```bash
    git commit -m "chore(integration): resolve 6-file conflict surface with upstream PR stack (PM #3208)" \
      -m "solver.py: PR generic f'{name}_out' fast path + config.equilibrators exact-match fallback stacked
    schema.py: local eos/splitter field family + PR geometry field family both preserved
    tests: PR topology rename (CD2_top) assertion values + local f-string assertion messages preserved
    verified: pytest tests/ full pass on integration/wang2022 (benchmark/e2e excluded by addopts)
    [Plan: exec-3208-integration-branch]"
    ```
  - ✅ 提交后检查：`git rev-list --parents -n 1 HEAD | wc -w` == 3（merge commit 双亲 = d7223f5 + 1f30492）
  - ✅ `git rev-parse main` == `d7223f5...`（main 全程未动）
  - ✅ `git log --oneline -1` 显示新 merge commit
  - ✅ 禁止 push：integration/wang2022 仅作存档（正式合并 #3209 只复用 6 文件解决内容，不走该分支的 GitHub merge 路径）
- **潜在风险**：误提交 plan 文件 → 负向检查兜底；双亲缺失（如误用了普通 commit）→ wc -w == 3 检查兜底
- **commit diff 范围说明**：该 merge commit 的实际 diff 除 6 个冲突文件外，还包含 PR8 带来的全部新增文件（src/h2iso/inventory/、src/h2iso/codegen/modelica_0d.py、tests/modelica/、tests/test_inventory/、tests/test_codegen/、wang2022_issi*.json 等）——这是 merge 语义的正常结果，不是执行污染；执行者不得因此清理或撤销这些文件
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

#### Task T4.2: 决策记录回写
- **目标**：把执行结果与分诊结论回写到本计划文件（不新建文件，避免排除项膨胀）
- **依赖**：T4.1 | **frontier**：否
- **执行者**：task-executor
- **修改内容**：在本计划文件末尾 `## Execution Log` 节追加：执行时间戳、integration/wang2022 的 merge commit SHA、C2 全量结果摘要（passed/failed 计数）、分诊结论（如有）、基线对照（T0.2）
- **修改边界**：只追加 Execution Log 节，不改动计划其余内容
- **质量检查方式**：`git status --porcelain=v1` 中 exec-3208 仍为 `??`（回写不影响 git 状态——文件本就 untracked）
- **验收标准**：
  - ✅ Execution Log 节已追加且含 commit SHA + pytest 摘要
- **潜在风险**：回写误删计划内容 → 用追加（append）而非覆盖
- **预留歧义标注**：
  - [ ] 无歧义
  - 歧义点：

---

## D1/D2 门控汇总

| 门 | 位置 | 通过条件 | 不通过动作 |
|----|------|---------|-----------|
| D1 | T1.3 末（进入 merge 前） | T1.1–T1.3 验收全过（SHA 无漂移、merge-base 正确、冲突清单恰为 4 文件、分支不存在、工作树干净） | STOP + NEEDS_USER_DECISION |
| D2 | T3.3 末（进入 commit 前） | C2 全量 pytest 全绿 | 6 文件外失败或修复轮次耗尽 → STOP + NEEDS_USER_DECISION（附四要素分诊报告） |

任务级终态验收：
- ✅ 当前分支 == integration/wang2022，HEAD 为双亲 merge commit（d7223f5 + 1f30492）
- ✅ 分支保留存档（不删除）
- ✅ main 未被修改（== d7223f5）
- ✅ 无任何 push / GitHub 交互
- ✅ 两个 plan 文件始终 untracked

---

## Execution Wave（并行执行波次）

| Wave | 可并行 Task | Frontier（无人挡即刻开工） | 依赖已完成 |
|------|------------|--------------------------|------------|
| W1 | T0.1, T0.2 | T0.1 | — |
| W2 | T1.1, T1.2, T1.3 | T1.1 | W1 |
| W3 | T2.1 | T2.1 | D1 |
| W4 | T2.2, T2.3, T2.4, T2.5, T2.6 | T2.2–T2.6（单执行器按序） | W3 |
| W5 | T2.7 → T3.1 → T3.2/T3.3 | T2.7 | W4 |
| W6 | T4.1 → T4.2 | T4.1 | D2 |

> 串行化理由（CoT Stage 4）：T2.1–T4.1 构成 git 状态机（MERGE_HEAD → stage-0 → commit），任一步乱序都会卡死索引；T2.2–T2.6 虽文件互不重叠可并行，但单执行器按序执行更安全，且彼此验收互不依赖。全部任务失败回滚策略：T2.x 内失败 → `git merge --abort`（soft）或 T5.2 硬回滚（见风险矩阵）；T3.x 失败 → 先分诊，回滚同前。

---

## Post-Execution Verification

### Automated Verification（Task Executor 自动执行）

| ID | 描述 | 命令 | 预期 |
|----|------|------|------|
| V1 | 6 文件无残留冲突标记 | `git grep -nE '^(<<<<<<<|>>>>>>>)' -- src/h2iso/flowsheet/schema.py src/h2iso/flowsheet/solver.py tests/test_flowsheet/test_isso_no_recycle.py tests/test_flowsheet/test_sweep.py tests/test_flowsheet/test_isso_full.py tests/test_flowsheet/test_schema.py` | 无输出 |
| V2 | 6 文件 ruff 通过 | `.venv/bin/python -m ruff check src/h2iso/flowsheet/schema.py src/h2iso/flowsheet/solver.py tests/test_flowsheet/test_isso_no_recycle.py tests/test_flowsheet/test_sweep.py tests/test_flowsheet/test_isso_full.py tests/test_flowsheet/test_schema.py` | exit 0 |
| V3 | 全量 pytest（= C2） | `timeout 2400 .venv/bin/python -m pytest tests/ -q --tb=short` | exit 0 |
| V4 | main 未被移动 | `git rev-parse main` | `d7223f5...` |
| V5 | 排除项未入版本库 | `git status --porcelain=v1 \| grep -E 'exec-3207\|exec-3208'` | 均为 `??` 前缀 |
| V1b | de-ai-fier 术语检查（本计划文件） | `de-ai-fier/deai_review_file(path=计划文件, doc_type="plan", strict=false)` | 记录摘要，不参与 blocking；MCP 不可用标注 `[⚠️ skipped]` |

### Manual Verification（真正需要人工判断）

- [ ] M1: 人工复核 T3.3 分诊报告（若产生）——判断"6 文件外失败"是否接受已知失败或授权扩围
- [ ] M2: 人工复核 integration/wang2022 的 merge commit 双亲与 message body，确认解决方案记录完整

---

## 风险与回滚矩阵

| # | 风险 | 影响 | 缓解 / 回滚 |
|---|------|------|-------------|
| R1 | pr/8 SHA 漂移（上游在执行期间 push） | 预演基于过期快照 | D1 捕获 → STOP + NEEDS_USER_DECISION（附漂移清单） |
| R2 | 冲突清单漂移（出现第 5 个冲突文件） | 决策原则不覆盖 | D1/T2.1 捕获 → `git merge --abort` → STOP + NEEDS_USER_DECISION |
| R3 | 本地 UQ/parity/CLI 测试对新 fixture 不兼容 | 6 文件外失败 | T3.3 分诊 → 不修改 → D2 STOP + 四要素报告；对照 T0.2 基线区分既有/引入 |
| R4 | 6 文件内冲突解决错误（字段序/四段顺序） | C1 失败 | T3.3 修复 ≤2 轮（仍守决策原则）；耗尽 → D2 STOP |
| R5 | merge 进行中误 checkout | 索引卡死/工作树损坏 | 全局约束：MERGE_HEAD 存在时禁止 checkout；若已发生 → 先 `git merge --abort` 再操作 |
| R6 | 排除项（两个 plan 文件）被误 stage | 污染 commit | 全流程禁止 `-A`；T2.7/T4.1 负向 grep 兜底 |
| R7 | 基线本身有红（main@d7223f5 全量非绿） | 分诊混淆 | T0.2 可选快照 + T3.3 第 4 步基线对照 |
| R8 | 预演不可行需放弃 | — | **soft（默认）**：`git merge --abort`（停留在 integration/wang2022 的 pre-merge 状态，供检查存档）→ NEEDS_USER_DECISION。**hard（放弃预演）**：`git merge --abort && git checkout main && git branch -D integration/wang2022`（main 全程未动，恢复即 checkout main；删除分支不违反"验证通过后保留"——未验证通过的放弃不保留） |

---

## 审查日志（Plan Architect 自审）

| 轮次 | 聚焦 | 发现问题数 | 已修正 | 剩余 |
|------|------|-----------|--------|------|
| R1 | 结构完整性（phase/task 模板字段、门控、wave） | 2 | 2 | 0 |
| R1.5 | 外部引用事实核查（SHA/ref 名/文件路径/merge-tree 实测/ruff/pytest 可用性） | 1 | 1 | 0 |
| R2 | 可执行性（命令逐条推导：merge 状态机、staging 语义、grep 计数验收） | 2 | 2 | 0 |
| R2.8 | LLM 可执行性（消除猜测空间：每文件精确 hunk 动作、检查命令、STOP 条件） | 1 | 1 | 0 |
| R3 | 风险与边缘（跨文件波及、回滚、授权归因、排除项） | 2 | 2 | 0 |
| **终止** | **[T5] — 全部审查轮 issue 清零** | | | **0** |

## Execution Log

### [2026-09-02] PM #3208 执行完成 — COMPLETED（含一次 D2 STOP + 用户授权扩围修复）

- **执行时间戳**: 2026-09-02（UTC+8，当日会话）
- **merge commit**: `6979a4d5707c5bcc1e4443c6087c1886b2f347e3`（integration/wang2022，双亲 = d7223f5bada9cb5f9df010b636edfa3e3aa1674d + 1f30492cc5a17410bf48dbd96dc445b791a3d597）
- **C2 全量 pytest 终态**: `512 passed, 1 skipped, 83 warnings in 907.42s` exit 0（benchmark/e2e 由 addopts 排除）
- **T0.2 基线对照**: main@d7223f5 全量 = `481 passed, 1 skipped, 83 warnings in 202.90s` exit 0（基线绿）
- **C1 定向子集**: `62 passed in 759.26s`（首轮 794.16s 亦通过；重跑数值略有波动属正常）
- **分诊结论（T3.3，一次触发）**:
  - 首轮 C2: `5 failed, 507 passed, 1 skipped` exit 1；失败全部在 `tests/test_uq/test_isso_uq.py`（TestIssoMCSanity×3 + TestIssoSobolScreening×2）
  - 根因: PR8 fixture `tests/fixtures/wang2022/wang2022_isso.json` 拓扑改名 `CD2_bottom_recycle`→`CD2_top`，与本地 `src/h2iso/uq/run_isso.py:154,160` 旧拓扑名过滤不兼容 → `ValueError: feed_stages length (2) != number of inputs (1)`（unit.py:89）
  - 判定: 失败文件 ∉ 6 文件集 → D2 STOP + NEEDS_USER_DECISION
  - **用户裁决（2026-09-02 会话）**: 选项 A 授权扩围修复——仅限 `src/h2iso/uq/run_isso.py` 第 154、160 行两处 `("CD2_bottom_recycle", "CD3_top")` → `("CD2_top", "CD3_top")`，与 6 文件内同模式一致；其余任何文件任何行不改
  - 修复后 grep 验证: 旧名计数 0、新名计数 2、ruff exit 0；重跑 T3.1（62 passed）+ T3.2（512 passed）全绿 → D2 通过
- **6 文件解决状态**: schema.py（2 hunk 双字段族，手工）、solver.py（1 hunk 四段叠加，手工）、test_isso_no_recycle.py（2 处，手工）、test_sweep.py（3 处，手工）、test_isso_full.py + test_schema.py（自动合并仅验证）
- **main 状态**: `d7223f5bada9cb5f9df010b636edfa3e3aa1674d`（全程未动）；无 push、无 GitHub 交互
- **排除项**: 两个 plan 文件全程 untracked（`??`），未入任何 staging/commit

```json
{
  "error_id": null,
  "plan": "exec-3208-integration-branch",
  "task": "PM #3208",
  "status": "COMPLETED",
  "merge_commit": "6979a4d5707c5bcc1e4443c6087c1886b2f347e3",
  "parents": ["d7223f5bada9cb5f9df010b636edfa3e3aa1674d", "1f30492cc5a17410bf48dbd96dc445b791a3d597"],
  "c2_result": {"passed": 512, "failed": 0, "skipped": 1, "exit": 0, "duration_s": 907.42},
  "baseline_t02": {"passed": 481, "failed": 0, "skipped": 1, "exit": 0, "duration_s": 202.90},
  "d2_stop_triggered": true,
  "d2_resolution": "user authorized option A: scope extension limited to src/h2iso/uq/run_isso.py lines 154,160 topology rename",
  "fix_files_outside_6": ["src/h2iso/uq/run_isso.py"],
  "main_unmoved": true,
  "excluded_plans_untracked": true,
  "pushed": false,
  "timestamp": "2026-09-02"
}
```
