# PM4012 T2 — 持久验收报告（真实 solver 机制修复与完整回归）

- **Task**: PM4012 T2（h2iso main CI 修复与完整回归）
- **Repo**: `/home/gw/opt/h2iso`（就地修复；**未** commit / push / PM 写）
- **Baseline**: T1 已提交 `8925e99`（HEAD）
- **Falsifier run（T2 机制证据）**: `FR-PM4012-8925e99-T2-20260925T0612Z`（`/tmp/opencode/pm4012/t2/`）
- **Report timestamp (UTC)**: `2026-09-25T08:40:00Z`
- **STATUS**: ✅ **RESOLVED — 方案2（≡ Option A，用户裁决）**；3-env 默认套件全绿；其余矩阵全绿；**未** commit / push / PM 写。
  - 目标非负性修复（`ipopt.bound_relax_factor=0.0`）在 AC11/AC14 **RED→GREEN**。
  - 该键引入的 2 个新质量平衡回归已按**用户裁决 Option A / 方案2**（扩白名单处理质量平衡测试）以**原理性、非掩盖**判据修正闭合：出现于进料的分量判据**不变**；零进料分量改用绝对容忍 `1e-5·F`（附非掩盖证明）。
  - 3 环境默认套件（py3.9/3.11/3.12，均 casadi 3.7.2）**全部 exit 0**。
  - **2026-09-29 复跑（T2b）**：方案2 在**当前工作树**（两测试文件重新处于旧判据状态）**重新落地**并复跑 RED→GREEN；目标集 **6 passed / exit 0**；详见 **§10**。

---

## 0. 预先门禁（严格，必须先于任何修复）

```
# 执行 T2 前
check_repair_preflight.py .github/plans/pm4012-repair-preflight.json
→ mode=strict violations=0 repair_allowed=True   (exit 0)   # preflight_t2.log

# Option A 扩白名单后复检
check_repair_preflight.py .github/plans/pm4012-repair-preflight.json
→ mode=strict violations=0 repair_allowed=True   (exit 0)   # preflight_t2_optionA.log
```
- **信任边界（照录，未弱化）**：`trust_boundary: internal consistency only — not authenticated; a PASS is not proof of independent execution`。`repair_allowed=true` ≠ 独立执行证明。

## 1. T2-S1 — 机制证据固化（只读引用）

引用 `/tmp/opencode/pm4012/t2/` 已落盘证据（sha256 见 §6）。关键数字：

| run | opts | conv | worst raw comp min | worst stream min |
|-----|------|------|--------------------|------------------|
| r1_default | stock | True | `-9.999999999999942e-09` | `-9.999999833425378e-09` |
| r2_brf0 | `bound_relax_factor=0` | True | **`+2.236e-22`** | `0.0` |
| r3_honor | `honor_original_bounds=yes` | True | `0.0` | `0.0` |
| r4_default ×3 | stock | True | `-9.999999999999942e-09`（**bit-identical ×3**）| `-9.9999999992e-09` |
| r5 | CI 同节点 pytest | — | **`1 passed in 72.14s`（CI 红本地未复现）** | — |

- 机制：**SURVIVED (HIGH)**。`neg_tol(1e-8)` 与 IPOPT 默认 `bound_relax_factor(1e-8)` **数值相等**（tolerance collision）。
- H2（约束不可行）**KILLED**（350 solve 全 `Solve_Succeeded`，tear<1e-4，mesh≤1.5e-6）；H3（输入缺陷为主因）**KILLED as cause**。
- **强制边界（照录，未豁免）**：**精确 CI 红（`< -1e-8`）本地未复现 = UNDECIDABLE**（`env311` default worst raw min 比 `-1e-8` 高 5.79e-23；CI 自身日志为进程内 1-ulp 翻面）。**未**把未复现归因环境/线程并当作证明。
- 边界正对照：恰在 `-1e-8` → ACCEPTED；`nextafter(-1e-8,-inf)` → REJECTED，错误串与 CI **逐字一致**（`got min=-1.000e-08`）。

## 2. T2-S2 — 实现（唯一一行键）

```
git diff src/h2iso/mesh/column.py  → 1 file changed, 1 insertion(+)
+            "ipopt.bound_relax_factor": 0.0,
```
- **仅**新增该键；未改 `max_iter` / `tol` / `sb` / `print_level`；**未**加 `honor_original_bounds`；**未** clip / post-project；**未**改 `stream.py` 的 `neg_tol`。
- `src/h2iso/mesh/column.py` sha256 `98acc7b8326f07fafc185636a1522facc8de6d52d1c2f22bd2cdc419e9e56673`（benchmark/e2e/wheel 运行期间与其一致 ⇒ 这些结果仍有效）。

## 3. T2-S3 — 目标回归测试（先 RED 后 GREEN，真实实测）

新增（白名单内）：
- `tests/test_flowsheet/test_isso_full.py::TestISSOFullNonNegativity::test_columns_and_streams_nonnegative` —— 真实 ISS-O 每列 `x/y_profile` + 每 stream `min >= 0.0`。
- `tests/test_mesh/test_column.py::TestColumnBoundRelaxation` —— (a) 捕获 `ca.nlpsol` 实参断言生产 `opts` 含 `bound_relax_factor == 0.0`；(b) 15-stage CD2 小列 `min(x/y_profile) >= 0.0`（秒级）。

| 测试 | 旧 opts | 新 opts |
|---|---|---|
| fast `TestColumnBoundRelaxation` | **2 failed**（`opts.get=None`；`x_min=-2.504e-14`）0.40s exit1 | **2 passed** 0.37s exit0 |
| `TestISSOFullNonNegativity`（env311，真实 ISS-O） | **1 failed**（`CD1 min=-9.77290993028844e-09`）95.95s exit1 | **1 passed** 72.13s exit0 |

## 4. 新失败 → 用户裁决 Option A → 判据修正（非掩盖）

### 4.1 现象（修复键引入的 NEW 回归）
新 opts 下 3 环境默认套件**一致**出现 2 个失败；旧 opts 下**均通过**（判别性实验）：

| 实验 | 命令 | exit | 结果 |
|------|------|------|------|
| 旧 opts（临时移除键） | `pytest …test_column::test_mass_conservation …test_continuation::test_mass_conservation_75` | **0** | 2 passed in 0.72s |
| 新 opts | 同上 | **1** | 2 failed in 0.77s（3/3 稳定） |

失败项：`tests/test_mesh/test_column.py::TestColumnSolve::test_mass_conservation`、`tests/test_mesh/test_continuation.py::TestContinuationN::test_mass_conservation_75`（后者原**不在**白名单）。

### 4.2 根因：零进料分量的相对分母病态
测试对 `feed_composition==0` 的分量用 `max(z_i, 1e-10)` 作相对分母，等价要求绝对闭合 ~`1e-14`，低于 IPOPT `tol=1e-8` 尺度。新 opts 下零进料痕量分量（H2/HD/HT）由 ~1e-14 升到 ~1e-11（**仍物理痕量**）：

| opts | 小列 `x_profile.min()` | comp0 绝对平衡 | 原 `rel_err` |
|------|------------------------|----------------|--------------|
| 旧 | `-2.504e-14`（<0） | `7.8e-21` | `7.8e-13` |
| 新 | `+1.0e-14`（≥0） | `1.5e-9` | `1.5e-1`（分母病态放大） |

75-stage 实测：零进料分量绝对平衡 `2.66e-10`（F=100），进料分量 `≤2.9e-10`。

### 4.3 用户裁决：**Option A**（扩白名单处理质量平衡测试）
**处置（原理性、最小、可证非掩盖）**：
- **进料分量判据不变**：`|balance| < 1e-4 · F · z_i`（未放宽）。
- **零进料分量**（`z_i==0`）：改用**绝对容忍** `|balance| <= 1e-5 · F`（约总流量的 0.001%）。理由：零进料无相对尺度；绝对残差受求解器约束容忍（IPOPT `tol=1e-8` × 流量尺度 ~`1e-6`）限制；`1e-5·F` 相对实测 `2.7e-10` 有 ~4×10^5 余量，且远高于最坏情形求解器残差（~`7.5e-5`）。
- 落地文件：`tests/test_mesh/test_column.py`、`tests/test_mesh/test_continuation.py`（两处同构修改）。
- **非掩盖证明**：新增 `tests/test_mesh/test_column.py::TestColumnSolve::test_mass_balance_criterion_detects_real_loss` —— 真实解通过（`|real[0]| <= 1e-5·F`）；注入 `1e-3` 零进料污染（H2）后**被拒**（`|bad[0]| > 1e-5·F`）。证明判据非恒真、可捕获真实越界。

## 5. T2-S4 — 完整回归矩阵（真实实测）

### 5.1 默认套件（3 真实环境，均 casadi 3.7.2；`OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`，各自 `timeout 2400`）

**Matrix 1（判据修正前；保留作回归证据）—— 3 环境一致 `2 failed`**
| 环境 | exit | 结果 |
|------|------|------|
| `/tmp/env39` py3.9.25 | **1** | 2 failed, 525 passed, 1 skipped, 3 xfailed（1083.61s） |
| `/tmp/env311` py3.11.12（=CI test-solver 同构） | **1** | 2 failed, 525 passed, 1 skipped, 3 xfailed（1158.75s） |
| `/tmp/opencode/pm4012/env312` py3.12.3 | **1** | 2 failed, 525 passed, 1 skipped, 3 xfailed（1190.50s） |

**Matrix 2（Option A 判据修正后；最终）—— 3 环境全部 `exit 0`**
| 环境 | exit | 结果 |
|------|------|------|
| `/tmp/env39` py3.9.25 | **0** | **528 passed, 1 skipped, 3 xfailed**（1981.18s） |
| `/tmp/env311` py3.11.12（=CI test-solver 同构） | **0** | **528 passed, 1 skipped, 3 xfailed**（2310.02s） |
| `/tmp/opencode/pm4012/env312` py3.12.3 | **0** | **528 passed, 1 skipped, 3 xfailed**（2364.32s） |

> `528` 比 Matrix 1 的 `525 passed` 多 1 个：新增非掩盖证明测试（收集总数 531→532）。
> ⚠️ **运行时间注意**：本轮 `env311` 2310s / `env312` 2364s，接近 `timeout 2400` 上限（租户负载下每套件 wall-time 波动大：Matrix 1 约 18–20 min，Matrix 2 约 33–40 min）。结论不受影响（均 exit 0），但 CI/重跑需留足 wall-time 余量。

### 5.2 其余矩阵（真实实测，全绿）
| 项 | env | exit | 结果 |
|----|-----|------|------|
| benchmark（3 passed，178.29s；isso_3col min 82.58s / cd2_75 577ms / bubble 157ms） | env312 | **0** | `benchmark_env312.log` |
| e2e pytest（真实 omc 1.27.0，8 passed 无 skip） | env312 | **0** | `e2e_pytest_env312.log` |
| e2e shell（真实 omc，"compiled cleanly"） | env312 | **0** | `e2e_shell_env312.log` |
| wheel clean smoke（`AC9_FINAL_EXIT=0`，smoke OK，8 passed） | — | **0** | `ac9_wheel.log` |
| lint `ruff check` / `ruff format --check`（pin 0.15.13 = CI 约束） | — | **0 / 0** | `lint_final2.log` |
| 定向 Option-A 三测试（2 质量平衡 + 非掩盖证明） | env311 | **0** | 3 passed in 2.39s，`optionA_targeted.log` |

### 5.3 V1b — de-ai-fier（计划文档，非阻断）
`deai_review_file(.github/plans/pm4012-ci-repair.md, doc_type="plan", strict=false)` → `passed=false, exit_code=2`；findings 以**文风**类为主（破折号/分号过用、长句、行号/版本号被误判 `number_without_unit`、1 处 `坏→坯` 误报出现于"损坏"）。按计划 V1b **记录摘要，不阻断**（不构成运行证据）。

## 6. 证据清单（sha256）

### 6.1 仓内改动（当前树）
| 文件 | sha256 |
|------|--------|
| `src/h2iso/mesh/column.py` | `98acc7b8326f07fafc185636a1522facc8de6d52d1c2f22bd2cdc419e9e56673` |
| `tests/test_flowsheet/test_isso_full.py` | `d851ccb48960ba12636f0256ec01f7d52ab2ff0a0ee23f6421420d4dc9b2c75b` |
| `tests/test_mesh/test_column.py` | `d3ab46554edd8b9f2dfbc16a80384f3f8c6fc647377556f3fbf4cd998907d121` |
| `tests/test_mesh/test_continuation.py` | `12acdc0594c80f5a0eb8d6e246bb04cedf4eda67ddace9f1173fb5d16e4bf9aa` |
| `.github/plans/pm4012-ci-repair.md`（文档） | `35bf8478e85ae62ee98de0efe5772c4ca8b8e9303f303e7544d6569a3b6c737f` |
| `.github/plans/pm4012-repair-preflight.json`（文档） | `b5213f834e0524cebcedf757fb28d4d20dae7b8c9760e4e3276c4392a40bf6dd` |

> 注：plan / packet / 本报告为**文档**；`column.py` 与两个测试文件的哈希为稳定运行证据。本报告**自指哈希不内嵌**，落盘后由外部记录。

### 6.2 T2 运行日志（`/tmp/opencode/pm4012/t2/`）
```
34634645e06fdeda62f172de9ce7ca22bfc46d6c6b25da577c759437137e5585  preflight_t2.log
34634645e06fdeda62f172de9ce7ca22bfc46d6c6b25da577c759437137e5585  preflight_t2_optionA.log
75068d91f61f3719affd6fe924880f1d89267c14c4ce17b4cac4be7bde3d121c  small_col_probe_oldopts.log
f960b8cbc099668d4818a160dfa4fdb3e3577d2cb4d50525757a81b4e5951b16  red_isso_nonneg_oldopts.log
dbc5e491cf2f47d62934722b3dbafa8a98beb06dda205583a0e36b38503b5236  green_isso_nonneg_newopts.log
85996674e24d5f38e1bc072ea88d3152bb0ce1e6bd851347df792d58e33e5ca0  lint_final.log
cf30c7fca7830d7dac48a11115a9dc41cdd32b88ef13e3e0eef6faa8b57081f2  lint_final2.log
25ad48d78f142e0b1fc079b9c2d37cb1dffd0c4ef3bf177de9665952c2db2040  ac9_wheel.log
ecbbaf650deaa48b358cf188ebc568a40b1f11c009aa70505bf489cca87bee8b  e2e_pytest_env312.log
a01a7b9586cfae06990d958e4d899e102787fba14c72dce733eb93c2e40ae7c0  e2e_shell_env312.log
d96c3f2afe61be9d6c872d9b8701266fea233e51aa68ab481943110e0c013ad0  benchmark_env312.log
3b46d7d9dc1feb101bdebcb4b621d4985bd0d9651616835fe4517ad3822b4762  benchmark_env312.json
c0e7a34eb774d5b6e42c9fe43e0f093028f7758c946fa3d108a2e9ef1a00dfa3  matrix_env39.log          (Matrix 1)
3cb4082363b816bfa9194faaefc5b72f1f357091feaf8db540ad6a6a164c8915  matrix_env311.log         (Matrix 1)
a143a8bbac8e8d3d07efd328ca4f1f2af4115fd937deaa85d3c489f4fd637654  matrix_env312.log         (Matrix 1)
c5898f5564a80c93433e6240a1b83fc3c9029a8971fc746f863677580987d083  matrix2_env39.log         (Matrix 2, GREEN)
fb5b2abf48a4ff5471739b24677edc8a0d826175f106d0f295eb327e5db9b96b  matrix2_env311.log        (Matrix 2, GREEN)
1a5802ca1eb1612a5aab928127dff9ca3e7676435145891f7950d967a955b44f  matrix2_env312.log        (Matrix 2, GREEN)
d6ae616cc22f19be3d01969fb37a383a6e3da3f641749d5b7dd889cde4e3fb2b  diag_oldopts_2tests.log
99ff1e7c93d1f127ef1564b75f2b8247078c893d75b53165e6c6f5915c7fcb15  diag_newopts_2tests.log
9589dec4d4bc1e3e9af6f45b415be1ca23d03fb831030d6a88569fddffda30a6  diag_newopts_3x.log
0ebd1614eb021eeade5d947be52d7964a69ddffe928d7b04cf3af82d3419d1a2  mb_probe_oldopts.log
3b763b53b316b5208371f36c22ce5c0097c8f5895796f2cc36090e2cec5ee40b  mb_probe_newopts.log
ca361d3371858fa3927482b51493052d9326fdd14f36cbd3d6844abf3eff87b8  mb75_probe_newopts.log
21e5dc9b7a8ffefe8ec5f0dec676c6af1e6b8566bf7e173cdf7900bd41472343  optionA_targeted.log
5915187243992b9895d223a3ce8696e9c320019a4903cd5bea8e1c42b5fb8a89  matrix_summary.txt
```

### 6.3 机制证据（T2 falsifier，只读引用）
```
c715b383358a6927ac31df92105470d6eed079130bcb3d26aa2d11fed2f73038  RUN.md
74b835b3c595326df5010908c79bc0d804b333fd22bdcd9ace85a0b5a8096591  r1_default.log
19a703ec252dbc0eb340e480a1456183003af5c3b1d6fa1dd476a40272e9cd6e  r2_brf0.log
cf00b5fdec7d26285661c77d971517c49f4f6305aa3b89c2e0ed49dca20ac9b8  r3_honor.log
7752ed484295426277ef27653558e1a309dd9eec293c4828918aeec03952c442  r4_default_rep3.log
81bd1c185fbcd73de363c40e8b9335907be3a4fc1eea06a1f336dc4ba926e862  r5_ci_node_repro.log
08354307b5768526024022d30d7862a6aa48f6a8577cdd509101697e1d1d851e  boundary_control.out
d416277ad9bfe8bd26f8395d663da61eb5cea44a9a9f59b9da59fdcb2666641b  ci_35761779052_failed.log
```

## 7. 验收矩阵（逐条）

| AC | 判据 | 状态 |
|----|------|------|
| AC1/AC2 | lint/format 绿（pin 0.15.13） | ✅ |
| AC7 | 默认套件绿（3 环境） | ✅ 528 passed / 1 skipped / 3 xfailed，exit 0（×3） |
| AC8 | benchmark 绿 | ✅ |
| AC9 | wheel clean smoke 绿 | ✅ |
| AC10 | e2e-modelica（pytest + shell）绿 | ✅（真实 omc 1.27.0） |
| AC11 | 真实 ISS-O 非负：RED→GREEN | ✅ |
| AC14 | 快速数值边界测试：RED→GREEN | ✅ |
| AC15 | 3-env 默认套件绿 | ✅（Matrix 2 全 exit 0） |
| AC16 | 本持久验收报告（RED/GREEN、环境、exit、UNDECIDABLE 边界、未覆盖项、非掩盖证明） | ✅ |
| AC12/AC13 | T1 新增持久回归（optional-solver / ci-configuration） | ✅（T1 `8925e99`，本轮未触碰） |

## 8. 未解决 / 未覆盖（剩余限制）

1. **UNDECIDABLE 边界（保留）**：CI 精确红（`< -1e-8`）本地未复现（`r5 = 1 passed in 72.14s`；`env311` default worst raw min 比 `-1e-8` 高 5.79e-23）。不得据"未复现"结案。
2. **wall-time 波动**：Matrix 2 的 `env312` = 2364s，逼近 `timeout 2400`；租户负载下每套件 33–40 min（Matrix 1 约 18–20 min）。CI/重跑需留足 wall-time。
3. **Option A 判据为受控例外**：零进料分量的绝对容忍（`1e-5·F`）为**用户授权**的测试判据修正；已附非掩盖证明。出现于进料分量的判据未变。
4. **慢测优化未做**：ISSI/ISSO 全流程为全套件主要耗时（计划列为 optimization，非本 T2 必须）。
5. 任务**未**标 done；**未** commit / push / PM 写。

## 9. 决策记录：NEEDS_USER_DECISION → **Option A**

- 提出（6 环境判别：旧通过/新失败 2 个质量平衡测试）→ 用户裁决 **A = 扩白名单处理质量平衡测试**。
- 执行：原理性判据修正（零进料绝对容忍）+ 非掩盖证明测试；白名单扩展 `tests/test_mesh/test_continuation.py`；packet/plan 同步；严格 preflight 复检通过（`repair_allowed=True`）。
- 结果：Matrix 2 三环境全绿（exit 0）。**未** commit（HEAD 仍 `8925e99`）。

## 10. T2b 复跑 — 方案2 在当前工作树重新落地（2026-09-29）

### 10.1 用户裁决（原文/来源，照录）

**原文（用户本轮消息，逐字）**：

> 用户明确选择方案2并授权实施：保留 src/h2iso/mesh/column.py 的 ipopt.bound_relax_factor=0.0 与
> tests/test_flowsheet/test_isso_full.py 严格非负回归；将零进料组分质量平衡判据改为绝对容忍 1e-5*F，
> 并保留/新增反掩盖测试（注入1e-3真实损失必须失败）。在 /home/gw/opt/h2iso 当前工作树继续执行，
> 先严格preflight packet exit0 repair_allowed=true。修改白名单仅：tests/test_mesh/test_column.py、
> tests/test_mesh/test_continuation.py、计划/验收报告必要更新；不要改生产质量平衡算法，不改stream neg_tol，
> 不clip，不加新方案。必须先在当前旧判据状态运行目标测试取得RED，再应用方案2，运行GREEN：两个原质量测试、
> 反掩盖测试、TestColumnBoundRelaxation、真实ISSO非负测试。把用户裁决原文/来源写入计划日志，
> 更新T2 acceptance报告；不commit/push/PM写。返回逐命令exit和diff范围。

**来源**：用户本轮会话直陈指令（2026-09-29）。**方案2 ≡ §9 Option A**（同一处置的不同指称）。

### 10.2 起跑状态差异（如实记录）

本轮进入时**工作树**中 `test_column.py`（`199fd92f…`）与 `test_continuation.py`（`efe0512b…`）
**处于旧判据状态**（上一轮 §4.3 的改动未保留）；`column.py`（`98acc7b8…`）与 `test_isso_full.py`
（`d851ccb4…`）的 T2 改动仍在。故本轮严格按用户指令：**旧判据取 RED → 重新落地方案2 → GREEN**。

### 10.3 逐命令 exit（完整）

| # | 阶段 | exit | 结果 |
|---|------|------|------|
| 1 | 严格 preflight | **0** | `violations=0 repair_allowed=True`（`preflight_t2b.log`, sha `71266998…`） |
| 2 | RED-1（旧判据，2 原质量测试） | **1** | 2 failed（comp0 `rel_err=1.52e-01` / `2.66e-02`） |
| 3 | RED-2（旧 opts 探针，临时移除键） | **1** | 2 failed + 1 error；ISSO 报 **CI 逐字错误** `got min=-1.000e-08` @ `stream.py:53`；`x_min=-2.504e-14` |
| 4 | 恢复 `column.py`（sha 断言） | **0** | sha `98acc7b8…`；diff +1 行 |
| 5 | 反掩盖变异探针（`1e-5*F`→`1e-1*F`） | **1** | TEST 可变红：`1.000e-01 accepted` ⇒ 判据非恒真 |
| 6 | GREEN（全目标集 6 项） | **0** | **6 passed in 134.25s**（env311 = CI test-solver 同构） |
| 7 | lint `ruff check` / `format --check`（pin 0.15.13） | **0 / 0** | 全仓 `All checks passed!` / `124 files already formatted` |

### 10.4 GREEN 目标集明细（`green_target_set_env311.log`）

```
test_column.py::TestColumnSolve::test_mass_conservation                              PASSED
test_column.py::TestColumnSolve::test_mass_balance_criterion_detects_real_loss       PASSED
test_column.py::TestColumnBoundRelaxation::test_build_nlp_disables_bound_relaxation  PASSED
test_column.py::TestColumnBoundRelaxation::test_small_column_profiles_nonnegative    PASSED
test_continuation.py::TestContinuationN::test_mass_conservation_75                   PASSED
test_flowsheet/test_isso_full.py::TestISSOFullNonNegativity::test_columns_and_streams_nonnegative  PASSED
======================== 6 passed in 134.25s ========================
```

### 10.5 方案2 语义（与 §4.3 一致，未变更）

- 进料分量：`|balance| < 1e-4*F*z_i`（**不变**）。
- 零进料分量（`z_i==0`）：`|balance| <= 1e-5*F`（绝对容忍；原 `max(z_i,1e-10)` 相对底座要求 ~1e-14 绝对闭合，低于 IPOPT `tol=1e-8`）。
- 判据以模块级 `_mass_balance_ok(balance, z_i, F)` 单点定义，供质量守恒测试与反掩盖测试共用（避免镜像漂移）。
- **未**改生产质量平衡算法 / `stream` neg_tol / clip / 新方案 / xfail / fixture。

### 10.6 范围与状态

```
git status --short
 M src/h2iso/mesh/column.py            (+1 行，保留)
 M tests/test_flowsheet/test_isso_full.py (保留)
 M tests/test_mesh/test_column.py       (方案2)
 M tests/test_mesh/test_continuation.py (方案2)
 M .github/plans/pm4012-ci-repair.md
 M .github/plans/pm4012-repair-preflight.json
?? .github/plans/pm4012-t2-acceptance.md
```
- 改动集合 == 白名单（两测试文件 + 计划/报告）；`column.py` 与 `test_isso_full.py` 为上一轮保留项。
- **未** commit（HEAD 仍 `8925e99`）；**未** push / 写 PM。
- 新增 sha：`test_column.py = 8ab8761d59fa04c6d3298476708c43b8ff694fd1fb8c7a4be4d6b08b17253472`；
  `test_continuation.py` 见 §10.7；`column.py = 98acc7b8…`（未变）。

### 10.7 证据清单 `/tmp/opencode/pm4012/t2b/`

```
preflight_t2b.log                 red1_oldcriterion_2masstests.log
red2_oldopts_relaxation_isso.log  mutation_antimasking.log
green_target_set_env311.log       column.py.keep  test_column.py.keep
```

---

## 11. P1 判据完备化（2026-10-09 追加）

- **用户裁决（原文）**：**「先 P1 判据再 P2 缺陷（推荐）」**（本轮会话直陈）。
- **内容**：判据统一为 `|balance| <= max(1e-5·F, 1e-4·F·z_i)`，覆盖**零进料**与**痕量非零 z**（ISS-O ppm 级）。
- **RED**：`test_mass_balance_criterion_covers_trace_feeds` 在旧判据下 **1 failed**（exit 1）。
- **GREEN**：`pytest tests/test_mesh/test_column.py tests/test_mesh/test_continuation.py -q` → **27 passed in 5.02s**（exit 0）；
  `ruff check`/`format --check` → exit 0/0。
- **反掩盖**：`test_mass_balance_criterion_detects_real_loss` 保留（注入 `1e-3·F` 损失被拒）。
- **回归**：`/tmp/opencode/pm4012/t2c/matrix_env311_p1.log`（env311 完整默认套件，P1 最终树）。
- **未解决（转 P2，单独立项）**：`column.py:278-282` 冷凝器级物料平衡漏进料项（`feed_stage=1` 静默丢弃整股进料）。
- **未** commit / push / PM 写（截至本节撰写）。

---

## 12. 三版本完整矩阵（P1 最终树，2026-10-09 追加）

commits: `8925e99`（T1）+ `9029aa9`（T2+P1）；workspace 干净。

| 环境 | 解释器 | 命令 | 结果 | exit |
|------|--------|------|------|------|
| py3.9 | 3.9.25 | `pytest tests/ -q` | 529 passed, 1 skipped, 3 xfailed (18:35) | 0 |
| py3.11 | 3.11.12 | `pytest tests/ -q` | 529 passed, 1 skipped, 3 xfailed (20:55) | 0 |
| py3.12 | 3.12.3 | `pytest tests/ -q` | 529 passed, 1 skipped, 3 xfailed (20:29) | 0 |

三环境均 `casadi==3.7.2`。日志：`/tmp/opencode/pm4012/t2c/matrix_env{39,311,312}_p1.log`。

**边界（如实）**：CI 精确红（`min<-1e-8`）本地未复现 = **UNDECIDABLE**；`nonneg` 回归依赖边界被精确 honor。
