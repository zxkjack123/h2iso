# PM4012 — h2iso main CI 修复与完整回归（T1 / T2）

**Mode**: generate（plan）→ refine（`[REFINE-1]`）
**Status**: IN_PROGRESS
**Scope Mode**: HOLD（bug 修复；严格保持范围，不扩不缩）
**Repo / workspace**: `/home/gw/opt/h2iso`（本仓，就地修复）
**Baseline**: `HEAD=49765f11e241da2ca9bee06837528deb1b824101`，`dirty=0`，`checkpoint=none`
**Falsifier run**: `FR-PM4012-49765f1-20260924T0248Z`
**Preflight packet**: `/home/gw/opt/h2iso/.github/plans/pm4012-repair-preflight.json`
**Authorization（授权归因，M5）**：
- ①授权主体：用户（本会话）
- ②授权时点与载体：本轮会话指令；**用户原文逐字**为 —— 补一次 "当前 main 的 CI 修复与完整回归验收"
- ③授权范围：对本仓 `/home/gw/opt/h2iso` 执行上述「当前 main 的 CI 修复与完整回归验收」，含**计划文件 / 测试 / 实现**变更
- **no-push 为默认策略（非用户引述）**：本计划默认不 push、不 commit 到远端。此为工作默认约定，**不**归因于用户原话，也不由本计划自行补全为「用户授权」。

> **Caveat（信任边界）**：本计划的 falsifier/preflight 证据均为**内部一致性**级别；`repair_allowed=true` **不**等于独立执行证明（`check_repair_preflight.py` trust_boundary 固定口径）。

---

## 0. 需求理解（CoT Stage 1）

```
REQUIREMENT: 修复 h2iso main 分支 CI 红灯（C1 casadi eager import / C2 py39 共用 312 约束 /
             C4 两个 key URL 404 / lint 8 + format 13），并对真实 solver 场景做再现修复与完整回归。
  ↓
CONSTRAINTS:
  - 授权仅限：计划/测试/实现变更；不 push。不引入新依赖运行时行为变化。
  - 不得改变物理容差（tolerances）与物理断言阈值；不得用 xfail/skip 掩盖故障。
  - 不得新增超出 CI 实际范围（`ruff check src/ tests/` + `ruff format --check src/ tests/`）的 format 要求。
  - 必须保留真实 `tests/test_flowsheet/test_isso_full.py` 场景为**未解决**边界：C3 简单 15-stage 列的
    KILLED 判定**不得**外推豁免 ISSO AC。
  - 真实矩阵缺环境（本机仅 py3.12）时，须先规划获取隔离环境；不得把模拟当实际验证。
  ↓
BOUNDARY (IN):  /home/gw/opt/h2iso 内 — .github/workflows/ci.yml、constraints/、src/h2iso/{_casadi 新增,
                mesh/*, inventory/calculator}、tests/{error_paths,test_uq,test_codegen,modelica,test_inventory,
                e2e,test_flowsheet} 的 CI 修复面。
BOUNDARY (OUT): 物理容差/断言阈值/参考数据 fixture、KNOWN_ISSUES_* xfail、pyproject 数值参数、
                tricys 等外部仓库（跨仓 ⇒ register+handoff，不在本仓修）、任何 push/远端提交。
  ↓
ACCEPTANCE (binary): 见 §4 的 frozen/current 验收清单（AC1–AC11）。全部为可执行判据。
```

**实测边界（本轮核验）**：
- 本机 Python：仅 `3.12.3`；`3.9`/`3.11` **不存在**（`uv 0.12.0`、`conda 26.5.3`、`docker 29.8.0` 可用 → 可获取隔离环境）。
- `omc`：`/home/gw/opt/om-1.27.0/usr/bin/omc`，`OpenModelica 1.27.0` **可用**（e2e 本地可跑）。
- `casadi 3.8.0`（本地）vs CI 约束 `casadi==3.7.2`；`ruff 0.16.5`（本地）vs `constraints/ci-3.12.txt:58 ruff==0.15.13`。
- **版本偏斜是 T1 确定性问题之一**：`lint-and-fast-test` 安装不 pin 的 `.[dev]`（拿到最新 ruff），其余腿 pin `ruff==0.15.13` → 同一提交可能得到不同 lint 结果。

---

## 1. 证据基线（全部实测，含 file:line 锚点）

### 1.1 C1 — casadi eager import（SURVIVED，决定性）

`import h2iso` 的 eager 链路（RED 复现命令见 T1）：
```
tests/test_species.py:3  from h2iso import SPECIES, Species
  src/h2iso/__init__.py:6            from h2iso.inventory import (...)
    src/h2iso/inventory/__init__.py:10  from h2iso.inventory.calculator import (...)
      src/h2iso/inventory/calculator.py:26  from h2iso.mesh.column import ColumnResult
        src/h2iso/mesh/__init__.py:3          from h2iso.mesh.column import Column, ColumnResult, ColumnSpec, FeedSpec
          src/h2iso/mesh/column.py:22           import casadi as ca
```
- 阻塞 casadi（`c1_blocker.py`，`sys.meta_path` 注入 blocker）后：**26 个 fast-test 模块全部 collection error**（`no tests collected, 26 errors`），退出码 3。
- 对照 `c1_control.py`（同一解释器、不阻塞）：`import h2iso OK`，退出码 0 → 归因于 casadi，非环境损坏。
- 影响面：`lint-and-fast-test`（装 `.[dev]`，无 casadi）、`test-wheel`（wheel 干净 venv + `pytest`，smoke 执行 `from h2iso.species ...`）、`benchmark`（装 `.[dev]` 但 `tests/benchmark/test_performance.py` 导入 `h2iso.flowsheet.solver` → casadi）。

### 1.2 C2 — py3.9 共用 3.12 约束（SURVIVED）

- `constraints/ci-3.12.txt:35 numpy==2.4.6`（`requires_python>=3.11`）被 `test` 矩阵 py3.9 腿复用 → `ResolutionImpossible`。
- 同类还需 ≥3.11 的 pin：`matplotlib==3.11.0(:27)`、`pandas==3.0.3(:38)`、`scipy==1.17.1(:60)`、`pytest==9.0.3(:49)`、`coverage==7.14.0(:11)`。
- 当前 `ci.yml:57/78` 三处 `-c constraints/ci-3.12.txt` 均无条件套用。

### 1.3 C4 — 两个 OpenModelica key URL 404（SURVIVED）

- `ci.yml:170-173` 的 `https://openmodelica.org/deb.openmodelica.org.gpg.key` 与 `.../build.openmodelica.org.key` → **HTTP 404**（证据：`50484c84.key`/`81d0084c.key` 均为 279 B 的 404 HTML）。
- 后果：dearmor 得到空 keyring → `apt-get update` `NO_PUBKEY 64CE41328E03B30A` → apt `exit=100`。
- **实测可用替代**：`https://build.openmodelica.org/apt/openmodelica.asc` → **HTTP 200**，正文 `-----BEGIN PGP PUBLIC KEY BLOCK-----`（77 行）。

### 1.4 LINT — ruff check 8 + format 13（SURVIVED）

`ruff check src/ tests/`（本地 0.16.5）→ 8 errors（7 auto-fixable）：
```
tests/e2e/test_modelica_cycle_integration.py:3:1  I001
tests/modelica/generate_overrides.py:19:1          I001
tests/modelica/generate_overrides.py:30:1          E402   （sys.path.insert 之后的 h2iso import；需 noqa）
tests/modelica/scalar_1d_mapping/plot_results.py:10:1   I001
tests/modelica/scalar_1d_mapping/run_simulation.py:9:1  I001
tests/modelica/vector_5d_mapping/plot_results.py:10:1   I001
tests/test_codegen/test_modelica_0d.py:3:1         I001
tests/test_codegen/test_modelica_0d.py:12:5        F401   （generate_column_override_lines 未使用）
```
`ruff format --check src/ tests/` → **13 个文件待格式化**（CI 实际范围 = `src/ tests/`，无超范围）：
```
src/h2iso/codegen/modelica_0d.py          src/h2iso/inventory/calculator.py
src/h2iso/inventory/models.py             src/h2iso/mesh/column.py
tests/e2e/test_modelica_cycle_integration.py
tests/modelica/generate_overrides.py      tests/modelica/scalar_1d_mapping/plot_results.py
tests/modelica/scalar_1d_mapping/run_simulation.py
tests/modelica/vector_5d_mapping/plot_results.py
tests/modelica/vector_5d_mapping/run_simulation.py
tests/test_flowsheet/test_issi_full.py
tests/test_inventory/test_column_inventory.py
tests/test_inventory/test_wang2022_inventory_benchmark.py
```

### 1.5 C3 — 边界场景**未排除**（简单列 KILLED ≠ ISSO 排除）— 本计划的关键判别

| 探针 | 场景 | min composition | vs Stream 阈值 `-1e-8` | 判定 |
|------|------|-----------------|------------------------|------|
| C3-A/B（falsifier） | 单列 15-stage CD2 | `-2.504e-14` | 4.6 个数量级余量 | KILLED |
| **C3-ISSO（本轮新增，真实 fixture）** | **完整 ISS-O（3 列 × 60 级 + 循环）** | **`-5.099508e-09`**（CD1.x_profile）/ `-4.475e-09`（CD2.x_profile） | **仅 ~2× 余量** | **UNDECIDABLE** |

- 复现：`python /tmp/opencode/falsifier_pm4012/c3isso_boundary_probe.py` → `converged=True iters=27 tear_residual=2.887e-06`，全 9 流 `Stream(...) -> ACCEPTED`，但 `CD1_bottoms.x_profile` 的最小分量已到 `-5.1e-9`。
- **结论（不得外推）**：C3 简单列的 KILLED **不构成**对全 ISSO 边界场景的豁免。真实 ISSO 的负分量余量比简单列小 4 个数量级，且当前**没有任何断言**覆盖「ISSO 全流程 min(composition) ≥ -1e-8」。
- `tests/test_flowsheet/test_isso_full.py` 实测：`10 passed in 574.21s`（**无断言失败**；风险是**运行时长**与**未覆盖的负分量边界**）——二者都必须在 T2 真实处理，不得以「测试已通过」宣称关闭。

---

## 2. 范围与边界（白名单 / 保护边界）

### 2.1 允许修改（白名单，T1）

| 组 | 文件 | 动作 |
|----|------|------|
| G1 optional import | `src/h2iso/_casadi.py`(新增) / `src/h2iso/mesh/column.py` / `src/h2iso/mesh/stage.py` / `src/h2iso/mesh/enthalpy.py` | 惰性 casadi 代理 + 3 处 import 替换 |
| G2 inventory 脱耦 | `src/h2iso/inventory/calculator.py` | `ColumnResult` 移入 `TYPE_CHECKING` |
| G3 solver 依赖测试守卫 | `tests/error_paths/test_solver_failures.py` / `tests/test_uq/test_integration.py` / `tests/test_uq/test_properties.py` | 模块级 / 类级 `pytest.importorskip("casadi")` |
| G4 lint 机械修复（8 errors / 7 文件，**全部列出**） | `tests/e2e/test_modelica_cycle_integration.py`(I001) / `tests/modelica/generate_overrides.py`(I001 + E402 noqa) / `tests/modelica/scalar_1d_mapping/plot_results.py`(I001) / `tests/modelica/scalar_1d_mapping/run_simulation.py`(I001) / `tests/modelica/vector_5d_mapping/plot_results.py`(I001) / `tests/modelica/vector_5d_mapping/run_simulation.py`(I001) / `tests/test_codegen/test_modelica_0d.py`(I001 + F401) | `ruff check --fix` + `# noqa: E402` |
| G5 format（CI 范围内 13 文件，**全部列出**） | `src/h2iso/codegen/modelica_0d.py` / `src/h2iso/inventory/calculator.py` / `src/h2iso/inventory/models.py` / `src/h2iso/mesh/column.py` / `tests/e2e/test_modelica_cycle_integration.py` / `tests/modelica/generate_overrides.py` / `tests/modelica/scalar_1d_mapping/plot_results.py` / `tests/modelica/scalar_1d_mapping/run_simulation.py` / `tests/modelica/vector_5d_mapping/plot_results.py` / `tests/modelica/vector_5d_mapping/run_simulation.py` / `tests/test_flowsheet/test_issi_full.py` / `tests/test_inventory/test_column_inventory.py` / `tests/test_inventory/test_wang2022_inventory_benchmark.py` | `ruff format` |
| G6 CI 确定性 | `.github/workflows/ci.yml`、`constraints/py3.9.txt`(新增)、`constraints/py3.11.txt`(新增) | C2 matrix include 映射 / test-solver 用 3.11 / C4 key / e2e+benchmark solver extra / ruff pin |
| G7 **持久回归测试（新增，必须带 RED）** | `tests/test_optional_solver.py`(新增) / `tests/test_ci_configuration.py`(新增) | C1 与 CI 配置不变量的常驻回归 |

> G5 与 G4 有 3 个文件重叠（`tests/e2e/test_modelica_cycle_integration.py`、`tests/modelica/generate_overrides.py`、`tests/test_codegen/test_modelica_0d.py`）：同一文件既被 `ruff check --fix` 排序、又被 `ruff format` 重排，属预期（先 `check --fix` 后 `format`）。

### 2.2 保护边界（⛔ 不得触碰）

- ⛔ 物理容差 / 断言阈值（受保护，不可为通过而放宽）：`pyproject.toml` 数值参数、tests 中的 `assert <阈值>`、`src/h2iso/flowsheet/stream.py:50` 的 `neg_tol` 语义、参考数据与 fixture。
- ✅ **受控例外（M4）— 经过证伪的 IPOPT 数值选项修复**：**允许**修改 **NLP 求解器数值选项**（如 `ipopt.bound_relax_factor`、`ipopt.tol`、`ipopt.acceptable_tol`、`ipopt.max_iter`、`ipopt.constr_viol_tol` 等），**当且仅当**同时满足：
  1. 有**判别性测试（discriminating test）**证据把越界/失败根因定位到该选项；
  2. 改动**不连带**放宽任何物理断言或 `Stream` 阈值；
  3. 附 **RED（改前复现）→ GREEN（改后通过）** 记录，且 `bound_relax_factor` 之类选项的方向与物理意义一致（不得为「让值变正」而调参掩盖真实越界）。
  - 反例（禁止）：把 `neg_tol` 从 `1e-8` 调到 `1e-6`、把 `assert min >= -1e-8` 放松为 `>= -1e-6`、或把 `bound_relax_factor` 设为掩盖负分量的非物理值。
- ⛔ 参考数据与 fixture：`tests/fixtures/wang2022/*.json`（只读）。
- ⛔ 已知问题标记：`tests/test_inventory/test_wang2022_inventory_benchmark.py` 的 `KNOWN_ISSUES_ISSI`/`KNOWN_ISSUES_ISSO` xfail —— **不得新增/删除/把 `xfail` 改成 `skip` 来掩盖故障**。
- ⛔ 不得把 T1 的 `importorskip` 用作掩盖真实 solver 故障的手段：只允许加在**确实需要 casadi 运行**的模块/类上（已逐一核验，见 T1）。
- ⛔ 跨仓：`tricys` 等外部仓库不在本仓修复；如需改动 → register + handoff。

### 2.3 非目标（Out of scope）

- 不重构 solver 数值算法；不更换 casadi/IPOPT 版本；不引入新运行时依赖。
- 不新增 CI job；不改 CI 触发条件（`on:`）。
- 不新增超出 `src/ tests/` 的 format/lint 范围。

---

## 3. 执行计划总览（2 任务）

| Task | 名称 | 目标 | 关键交付 |
|------|------|------|----------|
| **T1** | 确定性 CI / optional import / lint | 让 CI 在不装 solver 时也能 import 与跑 fast-test；lint/format 绿；py3.9 约束可解；OpenModelica 装机成功 | §4 T1 全部 AC1–AC6、AC8、AC9 |
| **T2** | 真实 solver 再现修复与完整回归 | 在**真实** full ISSO fixture 上再现并处理负分量边界；跑完整默认测试 + benchmark + e2e + wheel smoke + py3.9/3.11/3.12 矩阵 | §4 T2 全部 AC7、AC10、AC11 |

**依赖**：T2 的「根因调查」是**进入该阶段的前置条件（precondition）**，本计划**不**预置根因（不伪造）。T2 的**回归矩阵**可在 T1 完成后独立启动。

## 4. Phase T1 — 确定性 CI / optional import / lint

### Phase Record（入口三输入，进入 T1 前必写）

- **phase_goal**: 让 h2iso 在**不安装** optional solver（casadi）的环境下 `import h2iso` 成功、CI `lint-and-fast-test` 子集全绿；`ruff check`/`ruff format --check`（`src/ tests/` 范围）exit 0；py3.9 约束可解；OpenModelica apt 装机 exit 0。
- **phase_exit**: AC1–AC6、AC8、AC9 全部满足（逐条见下），且修改集合 == §2.1 白名单（`git diff --stat` 负向核验通过）。
- **accepted_baseline**: `HEAD=49765f1` clean；C1/C2/C4/LINT 四个 SURVIVED 判定为入场已接受事实；C3-ISSO 为 UNDECIDABLE（**不**在 T1 关闭）。

### Task T1 — 确定性 CI / optional import / lint

- **目标**：一次性把 main CI 的四类确定性红灯（C1 optional import / C2 py3.9 约束 / C4 key URL / LINT）修到绿，且不触碰物理容差与 xfail。
- **依赖**：无（frontier=是）
- **frontier**：是（T1 可即刻开工；T2 的 matrix 部分依赖 T1 的隔离环境就绪）
- **执行者**：Simulation Builder / Dev Orchestrator（本体就地执行）。所有编辑均在本仓 `/home/gw/opt/h2iso`。
- **修改内容（逐文件白名单，按有序步骤分组；每组独立 commit）**

#### 步骤 T1-S1 — 惰性 casadi（C1 核心，3 文件 + 1 新增）

- `src/h2iso/_casadi.py`（**新增**）：模块级惰性代理，暴露 `ca`（`__getattr__` 首次访问才 `importlib.import_module("casadi")`，失败时抛 `ImportError("h2iso.mesh requires the optional 'casadi' dependency; install it with: pip install 'h2iso[solver]'")`）。**不得**在 import 期加载 casadi。
- `src/h2iso/mesh/column.py:22`：`import casadi as ca` → `from h2iso._casadi import ca`
- `src/h2iso/mesh/stage.py:19`：同上（该文件 48 处 `ca.` 用法不变；`from __future__ import annotations` 已存在，注解保持惰性字符串）
- `src/h2iso/mesh/enthalpy.py:12`：同上（5 处 `ca.`）

#### 步骤 T1-S2 — inventory 层脱耦 + solver 依赖测试守卫（C1 测试侧，4 文件）

- `src/h2iso/inventory/calculator.py:26`：`from h2iso.mesh.column import ColumnResult` 移入 `if TYPE_CHECKING:`（该符号**仅**用于注解 line 31 与 docstring line 42；`from __future__ import annotations` 已在 line 10）。
- `tests/error_paths/test_solver_failures.py`：在 `import pytest` 之后加模块级 `pytest.importorskip("casadi")`（该模块 12 处 solver 调用，全部依赖 casadi）。
- `tests/test_uq/test_integration.py`：同模块级 `pytest.importorskip("casadi")`（该模块 4 处 solver 调用）。
- `tests/test_uq/test_properties.py`：**仅**为 `class TestPropertyInSolve` 加类级 autouse fixture `pytest.importorskip("casadi")`（该文件其余 4 个类为纯属性测试，**必须**在无 casadi 下继续运行，不得整模块 skip）。

#### 步骤 T1-S3 — lint 机械修复（2 文件，其中 E402 需人工）

- `tests/modelica/generate_overrides.py:30`：`from h2iso.codegen.modelica_0d import (  # noqa: E402`（`sys.path.insert` 在 import 前，属既定模式，加 noqa 而非重排）。
- `tests/test_codegen/test_modelica_0d.py`：`ruff check --fix` 移除未使用 import（line 12 `generate_column_override_lines`）并排序 import。
- 其余 I001（5 文件）由 `ruff check --fix` 机械排序。

#### 步骤 T1-S4 — format（CI 实际范围内 13 文件）

- 对 §1.4 列出的 13 个文件执行 `ruff format`。**不得**扩大范围到 `src/ tests/` 之外，**不得**顺手改数值/逻辑。

#### 步骤 T1-S5 — 每版本约束显式映射（C2：2 新增 + 2 修改）

- `constraints/py3.9.txt`（**新增**）、`constraints/py3.11.txt`（**新增**）：由各自解释器上的真实解析结果生成（依赖隔离环境；`constraints/ci-3.12.txt` **保留原名**用于 3.12）。
- `.github/workflows/ci.yml:42-57`（`test` job）：把 `matrix.python-version` 列表改为 **`include` 显式三元映射**（M1），并在 install 行消费 `matrix.constraints`：
  ```yaml
  strategy:
      matrix:
          include:
              - python-version: "3.9"
                constraints: constraints/py3.9.txt
              - python-version: "3.11"
                constraints: constraints/py3.11.txt
              - python-version: "3.12"
                constraints: constraints/ci-3.12.txt
  # install 步骤：
  #   pip install -c ${{ matrix.constraints }} -e ".[dev,solver]"
  ```
- `.github/workflows/ci.yml:73,78`（`test-solver` job，python **3.11**）：`-c constraints/ci-3.12.txt` → `-c constraints/py3.11.txt`（M1：同一 3.11 版本必须用同一约束文件，否则约束漂移）。
- **确定性加固（RUFF-PIN，optimization）**：`.github/workflows/ci.yml:20-23`（lint job）安装加 `-c constraints/ci-3.12.txt`，使 lint 与其余腿 ruff 版本一致。

#### 步骤 T1-S6 — OpenModelica key URL + solver extras（C4 / M2，1 文件）

- `.github/workflows/ci.yml:168-177`（e2e-modelica）：key 获取改为可验证来源 `https://build.openmodelica.org/apt/openmodelica.asc`（实测 HTTP 200 + 合法 PGP 公钥，含 CI 缺失的 `64CE 4132 8E03 B30A`），**去掉**对 404 URL 的 for/break 循环；`signed-by` 指向该 keyring。**保留** `deb [signed-by=...] https://build.openmodelica.org/apt $(lsb_release -cs) release`（实测 `dists/noble/Release` + `dists/noble/Release.gpg` + `dists/noble/release/binary-amd64/Packages` 均 200，component=`release` 正确）。
- `.github/workflows/ci.yml:181-182`（e2e-modelica job，**M2**）：`pip install -e ".[dev]"` → `pip install -e ".[dev,solver]"`（`tests/e2e/test_modelica_compile.py` 导入 `h2iso.mesh.column`/`ContinuationSolver`，需要 casadi）。
- `.github/workflows/ci.yml:139-140`（benchmark job）：`pip install -e ".[dev]"` → `pip install -e ".[dev,solver]"`（`tests/benchmark/test_performance.py` 导入 `h2iso.flowsheet.solver`，需要 casadi）。

#### 步骤 T1-S7 — 持久回归测试（**新增 2 文件，必须带 RED**）

- `tests/test_optional_solver.py`（**新增**）：C1 的**常驻**回归。用子进程 + `sys.meta_path` 注入 casadi blocker 后断言：
  1. `import h2iso` 成功且 `"casadi" not in sys.modules`；
  2. `import h2iso.mesh.column` 与 `from h2iso.flowsheet.solver import SequentialModularSolver` 成功（import 期不加载 casadi）；
  3. 真正调用求解器（如构造并 `Column(spec).solve()`）在无 casadi 时抛 `ImportError`，且消息含 `h2iso[solver]` —— 证明是**惰性**而非**静默失败**。
  - **RED**：当前在阻塞下 `import h2iso` 抛 `ModuleNotFoundError: casadi`（链路见 §1.1）→ 测试**失败**。
- `tests/test_ci_configuration.py`（**新增**）：CI 配置**不变量**回归（解析 `.github/workflows/ci.yml` + `constraints/`，非一次性脚本）。断言：
  1. `test` job 以 **`include` 显式映射**把 3.9→`constraints/py3.9.txt`、3.11→`constraints/py3.11.txt`、3.12→`constraints/ci-3.12.txt`，且三个文件均存在（M1）；
  2. `test-solver` job（3.11）使用 `constraints/py3.11.txt`（M1）；
  3. `benchmark` 与 `e2e-modelica` 的 install 含 `solver` extra（M2）；
  4. OpenModelica key URL == `https://build.openmodelica.org/apt/openmodelica.asc`，且**不含**两个 404 URL（`deb.openmodelica.org.gpg.key` / `build.openmodelica.org.key`）。
  - **RED**：当前 ci.yml 为单约束文件、两个 404 key URL、e2e/benchmark 仅 `.[dev]` → 测试**失败**。
- **持久性要求**：两文件必须被默认 `pytest tests/` 收集（不在 addopts 的 ignore 内），成为常驻回归。
- **反例（禁止）**：不得写成恒真断言（只 `assert Path.exists()` 而不校验映射内容）；不得只校验 HTTP 200 而不校验 key 身份（见 T1-S6 / AC6）。

- **修改边界（⛔）**：不得触碰 §2.2 保护边界；不得改 `pyproject.toml` 的容差/依赖下限（除 benchmark/e2e extra 的 CI 安装行，非 pyproject）；不得新增 `xfail`/`skip` 来替代真实修复；不得在 `src/` 引入 casadi 以外的 import 期副作用。
- **质量检查方式**：
  - 每步先跑该步的 **RED**（修复前必须复现失败），再跑 **GREEN**（exit 0）。
  - `git diff --stat` 负向核验：改动集合 == 本 Task 声明的文件；出现白名单外文件 → STOP。
  - 步骤 S1–S2 的 GREEN 必须**同时**在「casadi 被阻塞」与「casadi 可用」两种环境下成立。
  - **T1 只产出一个 commit**（含 S1–S7 全部改动；不分小步 commit）。

- **验收标准（可执行测试）**

**RED（修复前必须复现，逐一实测）**
```bash
cd /home/gw/opt/h2iso
# RED-C1: casadi 被阻塞时 import h2iso 失败（当前 exit 3）
python /tmp/opencode/falsifier_pm4012/c1_blocker.py ; echo "expect !=0, got $?"
# RED-fast: 无 casadi 时 fast-test 子集 26 个 collection error
PYTHONPATH=/tmp/opencode/nocasadi python3 -m pytest tests/ \
  --ignore=tests/benchmark --ignore=tests/e2e --ignore=tests/test_mesh \
  --ignore=tests/test_flowsheet --ignore=tests/property \
  --ignore=tests/test_uq/test_cd2_uq.py --ignore=tests/test_uq/test_isso_uq.py \
  --collect-only -q 2>&1 | tail -3 ; echo "expect errors>0"
# RED-LINT: ruff check 8 errors
.venv/bin/ruff check src/ tests/ ; echo "expect exit 1"
# RED-FORMAT: 13 files would be reformatted
.venv/bin/ruff format --check src/ tests/ 2>&1 | tail -1 ; echo "expect exit 1"
# RED-C2: py3.9 约束不可解
pip install --dry-run --python-version 3.9 -c constraints/ci-3.12.txt -e ".[dev,solver]" ; echo "expect exit 1"
# RED-C4: key URL 404
curl -s -o /dev/null -w '%{http_code}\n' https://openmodelica.org/build.openmodelica.org.key
# RED-S7a: 新增的 optional-solver 回归在修复前必须失败（当前 import 抛 ModuleNotFoundError）
.venv/bin/python -m pytest tests/test_optional_solver.py -q ; echo "expect FAIL (exit!=0)"
# RED-S7b: 新增的 CI 配置回归在修复前必须失败（当前单约束文件 + 404 key URL + 仅 .[dev]）
.venv/bin/python -m pytest tests/test_ci_configuration.py -q ; echo "expect FAIL (exit!=0)"
```

**GREEN（每步 T-A 命令型 / T-B 断言型）**
```bash
cd /home/gw/opt/h2iso
# [T-A] AC3 — 阻塞 casadi 后 import 成功（先重建 blocker harness）
mkdir -p /tmp/opencode/nocasadi && cat > /tmp/opencode/nocasadi/sitecustomize.py <<'PY'
import sys
class _B:
    def find_spec(self, name, path=None, target=None):
        if name == "casadi" or name.startswith("casadi."):
            raise ModuleNotFoundError(f"No module named '{name}' (blocked)")
        return None
sys.meta_path.insert(0, _B())
PY
PYTHONPATH=/tmp/opencode/nocasadi .venv/bin/python -c \
  "import h2iso, sys; assert 'casadi' not in sys.modules, 'casadi eagerly imported'; print('AC3 OK')"
python /tmp/opencode/falsifier_pm4012/c1_blocker.py ; echo "[T-A] AC3 exit=$? (expect 0)"
# [T-A] AC4 — 无 casadi 时 fast-test 子集全绿
PYTHONPATH=/tmp/opencode/nocasadi .venv/bin/python -m pytest tests/ \
  --ignore=tests/benchmark --ignore=tests/e2e --ignore=tests/test_mesh \
  --ignore=tests/test_flowsheet --ignore=tests/property \
  --ignore=tests/test_uq/test_cd2_uq.py --ignore=tests/test_uq/test_isso_uq.py \
  -q --tb=short ; echo "[T-A] AC4 exit=$? (expect 0)"
# [T-A] AC4b — 有 casadi 时被守卫的 3 模块仍然运行（不是被跳过）
.venv/bin/python -m pytest tests/error_paths/test_solver_failures.py \
  tests/test_uq/test_integration.py tests/test_uq/test_properties.py -q --tb=short
# [T-A] AC1/AC2 — lint + format 全绿（CI 实际范围）
.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ \
  && echo "[T-A] AC1+AC2 exit=0"
# [T-A] AC5 — py3.9 约束可解（需隔离环境，见下）
~/.local/share/uv/python/cpython-3.9*/bin/python -m pip install --dry-run \
  -c constraints/py3.9.txt -e ".[dev,solver]" ; echo "[T-A] AC5 exit=$? (expect 0)"
# [T-A] AC5b — test-solver(3.11) 约束可解
/tmp/env311/bin/python -m pip install --dry-run \
  -c constraints/py3.11.txt -e ".[dev,solver]" ; echo "[T-A] AC5b exit=$? (expect 0)"
# [T-A] AC6 — OpenModelica 装机 + 真实 fingerprint + Release 签名（docker 可用则**必须实跑**）
curl -fsSL https://build.openmodelica.org/apt/openmodelica.asc | gpg --dearmor > /tmp/om.gpg
gpg --show-keys --with-fingerprint /tmp/om.gpg \
  | grep -q "64CE 4132 8E03 B30A" && echo "[T-A] AC6-1 fingerprint(CI 缺失键) OK"
docker run --rm ubuntu:24.04 bash -lc '
  set -e
  apt-get update -qq && apt-get install -y -qq curl gnupg ca-certificates >/dev/null
  curl -fsSL https://build.openmodelica.org/apt/openmodelica.asc \
    | gpg --dearmor -o /usr/share/keyrings/openmodelica.gpg
  gpg --show-keys --with-fingerprint /usr/share/keyrings/openmodelica.gpg | grep -q "64CE 4132 8E03 B30A"
  echo "deb [signed-by=/usr/share/keyrings/openmodelica.gpg] https://build.openmodelica.org/apt $(. /etc/os-release; echo $VERSION_CODENAME) release" \
    > /etc/apt/sources.list.d/openmodelica.list
  apt-get update            # 必须 exit 0，且**无** NO_PUBKEY 64CE41328E03B30A
  apt-get install -y --no-install-recommends omc
  omc --version
'
echo "[T-A] AC6-2 apt Release 签名验证 + omc 安装 exit=$?"
# 若 `docker` 不可用（`command -v docker` 为空）⇒ 明确标 PARTIAL，**不得**标绿（见 §6 Deferred D1）
```

**能失败证明（Verify-RED）**：上述 RED 命令在修复前**逐一实测**（本轮已复现 C1 exit 3 / 26 collection errors / 8 lint errors / 13 format files / C2 ResolutionImpossible / C4 404）；若某条 GREEN 在修复前也通过，则该 GREEN 不具判别性，须替换。

- **隔离环境获取（真实矩阵缺环境时的前置，不得伪称已验证）**
```bash
# 本机仅 py3.12；用 uv 获取隔离解释器（不污染系统）
uv python install 3.9 3.11
uv venv --python 3.9  /tmp/env39 && /tmp/env39/bin/pip install -e ".[dev,solver]" -c constraints/py3.9.txt
uv venv --python 3.11 /tmp/env311 && /tmp/env311/bin/pip install -e ".[dev,solver]" -c constraints/py3.11.txt
# py3.9/3.11 上重跑完整默认套件（见 §6 矩阵）
# OpenModelica 装机需 sudo/容器：本机无 root ⇒ 用 docker ubuntu 复现 CI apt 步骤，或标 Deferred
```
> ⚠️ **诚实性硬规则**：py3.9/py3.11 腿与 e2e-modelica 的 apt 装机**只有在本机真实执行后**才可标记通过；在环境就绪前一律标 `⏸ PENDING ENV`，**禁止**用「设计已验证」替代「矩阵已实测」。

- **潜在风险**：
  1. `ruff 0.16.5`（本地）与 `0.15.13`（CI 约束）对 format/I001 判定可能不同 → 以 CI pin 为准复核；若冲突，以 `constraints/ci-3.12.txt` 的 ruff 版本重跑 AC1/AC2。
  2. `from h2iso._casadi import ca` 使 `ca` 由模块变为代理：若有代码做 `isinstance(ca, types.ModuleType)` 或依赖 `ca.__file__`，将行为变化 → 全仓 grep 确认无此类用法。
  3. benchmark job 加 `[solver]` 会延长其运行时间（可接受）。
- **预留歧义标注**（执行后回写）：
  - [ ] 无歧义
  - 歧义点：`constraints/py3.9.txt` / `py3.11.txt` 的**内容**需在各自解释器上实测生成（本计划不预置具体 pin，避免伪造）；生成命令见上。

---
## 5. Phase T2 — 真实 solver 再现修复与完整回归

### Phase Record（入口三输入，进入 T2 前必写）

- **phase_goal**: 在**真实** `tests/fixtures/wang2022/wang2022_isso.json`（ISS-O，3 列 × 60 级 + 双 tear 流）上**再现**并**用断言覆盖**「全流程 min(composition) 相对 Stream 阈值 `-1e-8` 的边界」；完成完整默认测试 + benchmark + e2e + wheel clean smoke + py3.9/3.11/3.12 矩阵回归。
- **phase_exit**: AC7 / AC10 / AC11 满足；且 AC11 的满足必须基于**真实 fixture 的实测证据**（raw output 落盘），**不得**引用 C3 简单列结论。
- **accepted_baseline**: T1 已完成（AC1–AC6、AC8、AC9 绿）；C3-ISSO = UNDECIDABLE（**未**排除）；`test_isso_full.py` 实测 `10 passed in 574.21s`（无断言失败，但**无**负分量断言）。

> **前置条件（precondition，进入 T2 前必须满足，禁止跳过）**
> 1. **本计划不预置 T2 根因**。根因必须由 T2 的实测证据确立；在证据齐备前，`root_claim` 保持 `asserted=false`（见 packet）。
> 2. **不得**以 C3 简单 15-stage 列的 KILLED 判定豁免 ISSO 边界 AC。若 T2 只复跑简单列 → AC11 判 **不满足**。
> 3. 隔离环境（py3.9/py3.11）与 OpenModelica 装机须真实就绪，否则对应矩阵项标 `⏸ PENDING ENV`，**不得**标通过。

### Task T2 — 真实 solver 再现修复与完整回归

- **目标**：把「ISSO 全流程负分量边界」从**未覆盖**变为**被断言覆盖**（必要时修复），并完成全矩阵回归。
- **依赖**：T1（隔离环境就绪）；本 Task 的**根因调查**为进入本 Phase 的前置条件。
- **frontier**：否（依赖 T1 的 optional import 与隔离环境）
- **执行者**：Simulation Builder + Dev Orchestrator（本体就地执行）
- **修改内容（T2 白名单 — 在调查结论出具后才最终冻结）**

> T2 的文件白名单**在根因证据确立后才冻结**；下方为**候选**范围，最终以调查结论为准（本计划不伪造根因，故不预写死实现文件）。

| 候选文件 | 触发条件 | 允许动作 |
|----------|----------|----------|
| `tests/test_flowsheet/test_isso_full.py` | 恒需要 | 新增「全 ISSO 负分量边界」断言（min(composition) ≥ `-1e-8`，覆盖 3 列 x/y profile + 9 条 stream）；**只增不减**，不得放宽既有断言 |
| `tests/fixtures/wang2022/wang2022_isso.json` | ⛔ 只读 | 不改 |
| `src/h2iso/flowsheet/stream.py` | **仅当**证据显示阈值语义错误 | 若需动，必须先证明 `-1e-8` 阈值本身是缺陷（而非 solver 产出越界）；**禁止**为通过而放宽容差 |
| `src/h2iso/mesh/column.py` 等 solver 文件 | **仅当**证据定位到具体数值缺陷 | 最小修复；IPOPT **数值选项**（`bound_relax_factor`/`tol`/`acceptable_tol`/`max_iter`/`constr_viol_tol`）**在满足 §2.2 M4 三条件时允许改**（须附 discriminating test + RED/GREEN，且不得连带放宽物理断言/`neg_tol`）|
| `tests/test_flowsheet/test_isso_full.py` 的 fixture 作用域 | optimization（可选） | 评估 function→module 作用域以消除 10 次重复 solve（574s）；**改后断言必须不变**，且需证据证明隔离性未被削弱 |

- **修改边界（⛔ 全部 Phase 共用）**
  - ⛔ 不得放宽/删除任何物理断言或阈值；⛔ 不得把 `xfail`/`skip` 作为通过手段（含 `strict=False` 的既存标记）；
  - ⛔ 不得改 `tests/fixtures/wang2022/*.json`；
  - ⛔ 不得引用 C3 简单列结论作为 AC11 证据；
  - ⛔ 不得把「`test_isso_full` 已 passed」等同于「ISSO 边界已覆盖」——**pass ≠ covered**。
- **质量检查方式**：
  - S1 的 **RED** 必须落盘 raw output（`/tmp` 或 `.github/plans/` 证据文件），并以 sha256 记录；
  - 新增断言必须通过 **Verify-RED**：在施加修复前，该断言必须**能失败**（反例锚定），否则该断言是装饰；
  - 全矩阵每条命令独立记录 exit code。

### 步骤

#### T2-S1 — 真实 ISSO 边界再现（RED，只读）
```bash
cd /home/gw/opt/h2iso
# RED: 全 ISSO 负分量边界（真实 fixture）——测量并落盘
.venv/bin/python /tmp/opencode/falsifier_pm4012/c3isso_boundary_probe.py \
  | tee /tmp/opencode/falsifier_pm4012/t2_isso_boundary_evidence.txt
# 期望观察（本轮已实测）：min=-5.099508e-09（CD1.x_profile），entries<-1e-8 = 0，余量仅 ~2x
# 判定：若 min < -1e-8 → 边界被击穿（进入 S2 修复）；
#       若 min >= -1e-8 → 仍须在 S3 增加回归断言把该边界锁定（未覆盖 → 已覆盖）。
```
- **能失败证明（Verify-RED）**：新增断言（min(composition) ≥ -1e-8）在**人为注入**一个 sub-`-1e-8` 分量（或把阈值临时上移，仅在验证脚本内）时必须失败；通过后再恢复。

#### T2-S2 — 根因定位与修复（条件执行；根因未证实则**不修**）
- 若 S1 击穿：以最小可复现（real fixture，固定 seed/初值）定位到具体列/级/组分；修复**仅**允许动 solver 数值缺陷，**禁止**动阈值。
- 若 S1 未击穿：记录余量与不确定性；**不**宣称根因，`root_claim` 保持 `asserted=false`；仅做 S3 的覆盖断言。
> 本计划**不**预设 S2 的根因与修复文件——由证据决定。

#### T2-S3 — 边界覆盖断言（真实 fixture，只增）
- 在 `tests/test_flowsheet/test_isso_full.py` 增加：对 `isso_full_result.column_results` 的每列 `x_profile`/`y_profile` 与 `isso_full_result.streams` 的每条 stream，断言 `min(composition) >= -1e-8`（与 `src/h2iso/flowsheet/stream.py:50` 的 `neg_tol` 同源）。
- 该断言**不得**替代既有温度/纯度/质量守恒断言；仅追加。

#### T2-S4 — 完整回归矩阵（见 §6，全矩阵逐条执行）

- **验收标准（可执行测试）**

**GREEN（全矩阵；每条记录 exit code）**
```bash
cd /home/gw/opt/h2iso
# [T-A] AC7 — 默认套件（addopts 已排除 benchmark/e2e）
.venv/bin/python -m pytest tests/ --tb=short ; echo "[T-A] AC7 exit=$?"
# [T-A] AC11a — 真实 ISSO 边界断言能失败（Verify-RED 反例锚定）
.venv/bin/python -m pytest tests/test_flowsheet/test_isso_full.py -q --tb=short ; echo "[T-A] AC11 exit=$?"
# [T-A] AC8 — benchmark（需 casadi；与 CI benchmark job 同构）
.venv/bin/python -m pytest tests/benchmark/ --benchmark-enable \
  --override-ini="addopts=" --benchmark-json=/tmp/benchmark_results.json ; echo "[T-A] AC8 exit=$?"
# [T-A] AC10 — e2e-modelica（本地 omc 1.27.0 可用）
.venv/bin/python -m pytest tests/e2e/ -v --override-ini="addopts=--benchmark-disable" ; echo "[T-A] AC10a exit=$?"
bash tests/e2e/test_tricys_init.sh ; echo "[T-A] AC10b exit=$?"
# [T-A] AC9 — wheel clean smoke（与 CI test-wheel job 同构；M3：用 uv build 避开本机缺 `build`）
rm -rf /tmp/opencode/h2iso-wheel && mkdir -p /tmp/opencode/h2iso-wheel \
 && uv build --wheel --out-dir /tmp/opencode/h2iso-wheel \
 && rm -rf /tmp/wheel-test-env && python3 -m venv /tmp/wheel-test-env \
 && /tmp/wheel-test-env/bin/pip install -q --upgrade pip \
 && /tmp/wheel-test-env/bin/pip install -q /tmp/opencode/h2iso-wheel/h2iso-*.whl pytest \
 && ( cd /tmp && /tmp/wheel-test-env/bin/python -c "from h2iso.species import SPECIES_ORDER, N_SPECIES; from h2iso.vle.mixing import bubble_pressure; from h2iso.equilibrator.exchange import equilibrium_composition; import numpy as np; x=np.array([0.5,0,0,0.5,0,0]); bubble_pressure(25.0,x); assert N_SPECIES==6 and len(SPECIES_ORDER)==6; print('smoke OK')" ) \
 && /tmp/wheel-test-env/bin/python -m pytest tests/test_data_resources.py -v -o "addopts=" ; echo "[T-A] AC9 exit=$?"
# 说明：CI 的 test-wheel job 自带 `pip install build`（ci.yml:96），其 `python -m build` 不变；
#       M3 仅替换**本地验证命令**，规避本机未装 `build` 的伪失败。
```

**能失败证明（Verify-RED）**：AC11 的边界断言在**未加**该断言时不存在（无覆盖）；加入后在注入 sub-`-1e-8` 分量的情况下必须失败（见 S1 的 Verify-RED）。

- **潜在风险**：
  1. `test_isso_full` 的 solve 时长非确定性（本轮 15s ~ 3.5min/次；整文件 574s）→ 全矩阵默认套件可能触发 CI 超时。
  2. 本地 `casadi 3.8.0` 与 CI `casadi==3.7.2` 的 IPOPT 默认 `bound_relax_factor` 可能不同 → 本地 `-5.1e-9` 与 CI 结果可能不一致；**必须在 py3.11+3.7.2 隔离环境复测**，不得沿用本地结论。
  3. py3.9 可能无 casadi wheel（3.7.2 支持性待实测）→ 该项标 `⏸ PENDING ENV` 直至实测。
- **预留歧义标注**（执行后回写）：
  - [ ] 无歧义
  - 歧义点：T2-S2 修复文件在根因证据出具前保持**未定**（有意留白，避免伪造根因）。

---

## 6. Post-Execution Verification（完整回归矩阵）

### Automated Verification（Dev Orchestrator / 执行者自动执行）

| ID | Description | Command | Expected |
|----|-------------|---------|----------|
| V1 | lint（CI 范围） | `.venv/bin/ruff check src/ tests/` | exit 0 |
| V2 | format（CI 范围，不超范围） | `.venv/bin/ruff format --check src/ tests/` | exit 0，`0 files would be reformatted` |
| V3 | optional import（casadi 阻塞） | `PYTHONPATH=/tmp/opencode/nocasadi .venv/bin/python -c "import h2iso"` | exit 0 且 `casadi` 不在 `sys.modules` |
| V4 | fast-test 子集（casadi 阻塞） | 见 T1 AC4 命令 | exit 0，0 failed |
| V5 | 默认套件 | `.venv/bin/python -m pytest tests/ --tb=short` | exit 0 |
| V6 | 真实 ISSO 边界断言 | `.venv/bin/python -m pytest tests/test_flowsheet/test_isso_full.py -q` | exit 0 |
| V7 | benchmark | 见 AC8 命令 | exit 0 |
| V8 | e2e-modelica pytest | 见 AC10a 命令 | exit 0（omc 可用） |
| V9 | e2e shell | `bash tests/e2e/test_tricys_init.sh` | exit 0 |
| V10 | wheel clean smoke | 见 AC9 命令（M3：`uv build`）| exit 0 |
| V11 | optional-solver 持久回归（**新增**） | `.venv/bin/python -m pytest tests/test_optional_solver.py -q` | exit 0（且 RED 阶段先 FAIL）|
| V12 | CI 配置不变量回归（**新增**） | `.venv/bin/python -m pytest tests/test_ci_configuration.py -q` | exit 0（且 RED 阶段先 FAIL）|
| V1b | de-ai-fier 术语检测（计划/packet） | `de-ai-fier/deai_review_file(path=.github/plans/pm4012-ci-repair.md, doc_type="plan", strict=false)` | 记录摘要，不阻断；MCP 不可用则标 `[⚠️ skipped]` |

### Matrix（py3.9 / 3.11 / 3.12）

| Leg | Env | Command | Status rule |
|-----|-----|---------|-------------|
| 3.12 | 本机 `.venv`（已实测） | V1–V10 | 可立即执行 |
| 3.11 | `uv venv --python 3.11 /tmp/env311` + `-c constraints/py3.11.txt` | `pytest tests/ -x --tb=short` | 环境就绪后执行；否则 `⏸ PENDING ENV` |
| 3.9 | `uv venv --python 3.9 /tmp/env39` + `-c constraints/py3.9.txt` | `pytest tests/ -x --tb=short` | 环境就绪后执行；否则 `⏸ PENDING ENV` |

### Deferred (needs restart / deployment)
- [ ] D1: OpenModelica apt 装机（`apt-get update && apt-get install -y omc`）——需 sudo/容器。**本机 `docker 29.8.0` 可用 ⇒ 必须按 AC6 的 docker 命令实跑**（含 fingerprint + Release 签名验证）；**仅当** `command -v docker` 为空时标 `⏸ PARTIAL (no docker)`，**禁止**在未实跑时标绿。CI runner 侧由 e2e-modelica job 复验。
- [ ] D2: ubuntu:24.04 `VERSION_CODENAME=noble` 与 CI runner 的 `lsb_release -cs` 一致；若 runner 换版，`dists/<codename>` 需另测（本轮仅验 `noble`）。

### Probe (best-effort, run if available)
- [ ] P1: `curl -s -o /dev/null -w '%{http_code}' https://build.openmodelica.org/apt/openmodelica.asc` → 200
- [ ] P2: `command -v omc && omc --version` → OpenModelica 1.27.0

### Manual（真正需要人工判断）
- [ ] M1: 人工阅读 `t2_isso_boundary_evidence.txt`，确认 `min(composition)` 余量与结论一致（不得由脚本自动宣称「已排除」）。
- [ ] M2: 人工确认 `git diff` 未触碰 §2.2 保护边界（容差/xfail/fixture）。

---

## 7. Execution Wave

| Wave | 可并行 Task | Frontier | 依赖已完成 |
|------|------------|----------|------------|
| W1 | T1（S1→S2→S3→S4→S5→S6→S7 串行；**T1 只产出一个 commit**，不分小步 commit） | T1 | — |
| W2 | T2（S1→(S2)→S3→S4） | T2 | W1（隔离环境） |

---

## 8. 审查日志

| 轮次 | 聚焦 | 发现问题数 | 已修正 | 剩余 |
|------|------|-----------|--------|------|
| R1 | 结构完整性（2 任务 / Phase Record 三字段 / 白名单） | 2 | 2 | 0 |
| R1.5 | 外部引用事实核查（file:line / URL / 版本 / 环境） | 3 | 3 | 0 |
| R2 | 可执行性（RED/GREEN 命令干跑） | 2 | 2 | 0 |
| R2.8 | LLM 可执行性（歧义消解） | 1 | 1 | 0 |
| R3 | 风险与边缘（跨轮一致性） | 2 | 2 | 0 |
| **[REFINE-1]** | CT 必改 M1–M5 + 持久回归测试 + 单 commit + Status | 7 | 7 | 0 |
| **终止** | **T3 — 无剩余 issue，且 RED 均已实测复现** | | | **0** |

**R1.5 事实核查要点**：①`build.openmodelica.org/apt/openmodelica.asc` 实测 200 + PGP 头；②`casadi` 仅 3 处 mesh 模块 + 1 处 `vle/souers.py:202` 惰性；③本机无 py3.9/3.11（已标 PENDING ENV，未伪称）。

---

## 9. Phase Record（机读，供 `check_progressive_delivery.py::validate_phase_record`）

```json
{
  "phase_goal": "T1: 让 h2iso 在无 casadi 环境 import 成功且 CI fast-test/lint/format/每版本约束(3.9/3.11/3.12)/OpenModelica装机(含 fingerprint+Release 签名)全绿，并落地 2 个持久回归测试",
  "phase_exit": "AC1-AC6, AC8, AC9 全绿且 git diff 仅落在白名单；tests/test_optional_solver.py 与 tests/test_ci_configuration.py 均先 RED 后 GREEN；T1 单 commit",
  "accepted_baseline": "HEAD=49765f1 clean; C1/C2/C4/LINT SURVIVED; C3-ISSO UNDECIDABLE",
  "blocking_acceptance": [
    {"command": ".venv/bin/ruff check src/ tests/", "exp_exit": 0, "class": "blocker"},
    {"command": ".venv/bin/ruff format --check src/ tests/", "exp_exit": 0, "class": "blocker"},
    {"command": "PYTHONPATH=/tmp/opencode/nocasadi .venv/bin/python -c 'import h2iso'", "exp_exit": 0, "class": "blocker"},
    {"command": ".venv/bin/python -m pytest tests/test_optional_solver.py tests/test_ci_configuration.py -q", "exp_exit": 0, "class": "blocker"},
    {"command": ".venv/bin/python -m pytest tests/test_flowsheet/test_isso_full.py -q", "exp_exit": 0, "class": "blocker"}
  ],
  "accepted_issues": [
    {"issue": "C3-simple KILLED 不得外推至 ISSO 边界", "plan_ref": ".github/plans/pm4012-ci-repair.md#15", "effect": "ISSO 边界保持 UNDECIDABLE，由 T2 真实 fixture 覆盖"}
  ],
  "optimizations": ["ruff 版本 pin（消 lint 腿版本偏斜）", "test_isso_full fixture 作用域评估（574s → 更低）"],
  "budget": {"max_candidates": 6, "max_minutes": 240, "max_network_calls": 10},
  "spent": {"candidates": 6, "minutes": 0, "network_calls": 4}
}
```

---

## 10. 交付物（绝对路径）

| 交付物 | 路径 |
|--------|------|
| 本计划 | `/home/gw/opt/h2iso/.github/plans/pm4012-ci-repair.md` |
| Repair-preflight packet | `/home/gw/opt/h2iso/.github/plans/pm4012-repair-preflight.json` |
| 边界证据（T2-S1 落盘） | `/tmp/opencode/falsifier_pm4012/t2_isso_boundary_evidence.txt` |

**→ handoff: dev-orchestrator**（按 W1 → W2 执行；T2 进入前须先满足 §5 前置条件）

---

## 11. Execution Log — T1（就地执行，2026-09-24）

> 执行者：Simulation Builder（本体就地执行）。**未** commit / push / 写 PM；未改外仓。
> 预先门禁：`python3 /home/gw/opt/copilot-agents/scripts/check_repair_preflight.py .github/plans/pm4012-repair-preflight.json`
> → `mode=strict violations=0 repair_allowed=True`（exit 0，`/tmp/opencode/pm4012/preflight.log`）。

### 11.0 证据文件白名单声明（写本 Log 的前置条件）

本节及其引用的证据文件，**声明加入本计划的交付物白名单**（§10 扩展）：证据文件为
`/tmp/opencode/pm4012/*.log|*.exit`（RED/GREEN 原始命令退出码日志，见 11.2/11.3），
本计划文件 `.github/plans/pm4012-ci-repair.md` 的 §11 为唯一仓内 Execution Log 落点。
除此之外仓内改动集合 == §2.1 白名单（见 11.1 负向核验）。

### 11.1 改动集合（负向核验：`git diff --name-only` + `git status --short`）

**修改（20 tracked）**：`.github/workflows/ci.yml`、`src/h2iso/{codegen/modelica_0d.py, inventory/calculator.py, inventory/models.py, mesh/column.py, mesh/enthalpy.py, mesh/stage.py}`、
`tests/e2e/test_modelica_cycle_integration.py`、`tests/error_paths/test_solver_failures.py`、
`tests/modelica/{generate_overrides.py, scalar_1d_mapping/plot_results.py, scalar_1d_mapping/run_simulation.py, vector_5d_mapping/plot_results.py, vector_5d_mapping/run_simulation.py}`、
`tests/test_codegen/test_modelica_0d.py`、`tests/test_flowsheet/test_issi_full.py`、
`tests/test_inventory/{test_column_inventory.py, test_wang2022_inventory_benchmark.py}`、
`tests/test_uq/{test_integration.py, test_properties.py}`。

**新增（5）**：`src/h2iso/_casadi.py`、`tests/test_optional_solver.py`、`tests/test_ci_configuration.py`、
`constraints/py3.9.txt`、`constraints/py3.11.txt`。

**保护边界核验（M2）**：`pyproject.toml`、`tests/fixtures/wang2022/*`、`src/h2iso/flowsheet/stream.py`、
`build/`、`site/`、`*.egg-info/` **均未触碰**（`git status` 为空）。格式类改动经逐文件复核为**纯换行/尾逗号重排**；
`tests/test_inventory/test_wang2022_inventory_benchmark.py` 的断言阈值与 `KNOWN_ISSUES_*` `xfail` 标记**逐字未变**
（仅 assert message 加括号换行）。全仓 `git diff` 内**无新增 xfail/skip**（唯 3 处 `pytest.importorskip("casadi")` 守卫）。

### 11.2 RED（修复前实测，全部复现）

| ID | 命令 | exit | 证据 |
|----|------|------|------|
| RED-C1 | `PYTHONPATH=/tmp/opencode/nocasadi .venv/bin/python -c "import h2iso"` | 1 | `/tmp/opencode/pm4012/red_c1.log` |
| RED-fast | fast 子集 `--collect-only`（阻塞 casadi） | 2（26 collection errors） | `red_fast.log` |
| RED-LINT | `.venv/bin/ruff check src/ tests/` | 1（8 errors） | `red_ruff_check.log` |
| RED-FORMAT | `.venv/bin/ruff format --check src/ tests/` | 1（13 files） | `red_ruff_format.log` |
| RED-C2 | `/tmp/env39` 内 `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"` | 1（ResolutionImpossible） | `red_c2.log` |
| RED-C4 | `curl` 两个 OpenModelica key URL | 404 / 404（替代 200） | `red_c4.log` |
| RED-S7a | `pytest tests/test_optional_solver.py -q` | 1（3 failed） | `red_s7a.log` |
| RED-S7b | `pytest tests/test_ci_configuration.py -q` | 1（5 failed） | `red_s7b.log` |

### 11.3 GREEN（T1 范围，逐条退出码）

| AC | 命令（简） | exit | 结果 |
|----|-----------|------|------|
| AC1 | `/tmp/ruff013/bin/ruff check src/ tests/`（**pin 0.15.13**） | 0 | All checks passed |
| AC2 | `/tmp/ruff013/bin/ruff format --check src/ tests/` | 0 | 124 files already formatted |
| AC3 | 阻塞 casadi `import h2iso` + `casadi not in sys.modules` | 0 | — |
| AC4 | 阻塞 casadi fast 子集（CI ignore 集） | 0 | 276 passed, 6 skipped |
| AC4b | 有 casadi：`error_paths/test_solver_failures.py` + `test_uq/test_integration.py` + `test_uq/test_properties.py` | 0 | 32 passed（0 skip） |
| AC5 | `/tmp/env39` 内 **真实** `pip install -c constraints/py3.9.txt -e ".[dev,solver]"`（D2 裁决后重跑） | 0 | 装上 `casadi==3.7.2`；re-freeze 与文件 **0 drift** |
| AC5b | `/tmp/env311` 内 **真实** `-c constraints/py3.11.txt` | 0 | 装上 `casadi==3.7.2`；re-freeze 与文件 **0 drift** |
| AC6-1 | `curl …/openmodelica.asc` → 4780 B PGP；`gpg --show-keys --with-fingerprint` | 0 | 含 `64CE 4132 8E03 B30A` |
| AC6-2 | `docker run --rm --network=host ubuntu:24.04` apt 装 omc | 0 | `OpenModelica 1.27.1`，`NO_PUBKEY` 计数 0 |
| AC8 | `.venv/bin/python -m pytest tests/benchmark/ --benchmark-enable --override-ini="addopts=" --benchmark-json=…` | 0 | **3 passed**（119.68 s）；cd2_75=1.055 s / isso_3col=58.17 s / bubble_1000x=0.147 s |
| AC9 | `uv build --wheel` + 纯净 venv smoke + `test_data_resources.py` | 0 | smoke OK（clean venv 无 casadi，惰性导入成立）+ 8 passed |
| AC12 | `pytest tests/test_optional_solver.py` | 0 | （与 AC13 合并 8 passed） |
| AC13 | `pytest tests/test_ci_configuration.py` | 0 | 5 passed |
| 定向 solver | `pytest tests/test_mesh -q` | 0 | 78 passed |

**守卫行为双向验证**：有 casadi → 3 模块全跑（32 passed，0 skipped）；阻塞 casadi → `test_solver_failures.py` / `test_integration.py` 整模块 skip（exit 5 = 无测试运行，属预期），`test_properties.py` 仍 14 passed + 1 skip（仅 `TestPropertyInSolve` skip）。

### 11.4 隔离环境路径（真实，非模拟）

| 用途 | 路径 | 说明 |
|------|------|------|
| py3.9 | `/tmp/env39` / `/tmp/verify39` | uv 装 `cpython-3.9.25`；约束由真实 install freeze 生成 |
| py3.11 | `/tmp/env311` / `/tmp/verify311` | uv 装 `cpython-3.11.12` |
| pin ruff | `/tmp/ruff013` | `ruff 0.15.13`（= `constraints/ci-3.12.txt`） |
| wheel 验证 | `/tmp/wheel-test-env`、`/tmp/opencode/h2iso-wheel/` | 干净 venv + `uv build` wheel |
| 日志 | `/tmp/opencode/pm4012/` | 全部命令退出码日志（含 `preflight.log`） |
| 阻塞 harness | `/tmp/opencode/nocasadi/sitecustomize.py` | `sys.meta_path` casadi blocker |

约束生成：各自解释器 `pip install -e ".[dev,solver]"`（真实解析）→ `pip freeze --exclude-editable`
（剔除 pip/setuptools/wheel/h2iso）→ 排序落盘；并补 `ruff==0.15.13` 以跨腿统一 lint 版本；
D2 裁决后 casadi pin 由 `3.8.1` 统一回 **`3.7.2`**（见 §11.7）。

### 11.5 执行内偏离（均已最小化并说明）

1. **守卫位置**：`test_solver_failures.py` / `test_integration.py` 的模块级 `importorskip` 置于**完整 import 块之后**（非 `import pytest` 之后），以规避 `E402`（import 前有语句）。语义等同。
2. **TYPE_CHECKING 形式**：`src/h2iso/mesh/{stage,enthalpy}.py` 采用
   `if TYPE_CHECKING: import casadi as ca / else: from h2iso._casadi import ca`，
   以使注解中的 `ca.SX` 对类型检查器仍有效（plan 的字面 `from h2iso._casadi import ca` 会产生约 40 条
   “Variable not allowed in type expression” IDE 报错）。运行期行为与计划一致。
3. **约束生成走 aliyun 镜像**：本机直连 pypi.org TLS 不可用（本地代理 `127.0.0.1:7890`），
   改用 `https://mirrors.aliyun.com/pypi/simple/`；解释器为 uv 真实隔离环境，非 dry-run 伪造。

### 11.6 未解决 / PARTIAL（移交 T2，**未**放宽任何验收）

| AC | 状态 | 原因 |
|----|------|------|
| AC7（默认完整套件） | ⏸ PENDING（T2） | 含 `test_flowsheet`（实测 574 s），按任务约定「全矩阵可 T2 执行」 |
| AC10（e2e-modelica pytest） | ⏸ PENDING（T2） | 本机 `omc 1.27.0` 可用；按约定留 T2 |
| AC11（ISSO 负分量边界） | ⏸ PENDING（T2） | 本计划既定：T1 不关闭 C3-ISSO |
| py3.9/3.11 **完整 pytest 矩阵** | ⏸ PENDING（T2） | T1 仅验「约束可解 + 真实安装 + solver smoke」；未在隔离环境跑完整套件 |
| ~~casadi 版本偏斜~~ | ✅ **已关闭（D2 用户裁决）** | 用户选择「统一保留 3.7.2」→ `py3.9.txt`/`py3.11.txt` 的 casadi pin 由 3.8.1 改为 **`3.7.2`**，三套 CI 约束 casadi 统一、**未升级**。证据见 §11.7。 |
| ~~benchmark/e2e 浮动 casadi~~ | ✅ **已关闭（D1 细化）** | 两 job 加 `-c constraints/ci-3.12.txt`；新增不变量先 RED 后 GREEN；env312 同构 benchmark GREEN。见 §11.8 / §11.9。 |
| 计划 §2.1 G4 表 | ℹ️ 记录 | G4 表把 `tests/modelica/vector_5d_mapping/run_simulation.py` 列为 I001 文件，实际 ruff 未对该文件报 I001（仅进入 §1.4 的 format 集）。属计划列举冗余，无功能影响。 |

**结论**：T1 的 9 个冻结 AC（AC1–AC6、AC8、AC9）+ 2 个持久回归 AC（AC12、AC13）**全部满足**；
其中 AC8 的**同构**证据为 env312（3.12 + `ci-3.12.txt`，casadi 3.7.2）实跑 GREEN，`.venv`(3.8.0) 结果仅作**非同构补充**。
「三腿 casadi 统一 `3.7.2`」已闭合（D2：py3.9/py3.11 约束改 pin；D1：benchmark/e2e 加 `-c`）。
且修改集合 == §2.1 白名单（+ 计划 §11 Log）、保护边界未触碰、无新增 xfail/skip、无 commit/push/PM 写。
其余 AC（AC7 / AC10 / AC11 + 完整矩阵）按计划归属 **T2**，本 Log **不**以任何“设计已验证”替代实跑。

### 11.7 用户裁决记录（D2）与 casadi 统一执行（2026-09-24 追加）

**用户原选项（逐字）**：`统一保留3.7.2（推荐）`。
**授权范围（用户表述）**：三套 CI 约束 CasADi 统一 `3.7.2`，**不升级**。

**执行动作**：
- `constraints/py3.9.txt`、`constraints/py3.11.txt`：`casadi==3.8.1` → **`casadi==3.7.2`**（与 `constraints/ci-3.12.txt` 一致）；其余 pin 未动。
- 真实环境安装验证（非 dry-run，走 aliyun 镜像）：
  | Env | 命令 | exit | casadi | 一致性 |
  |-----|------|------|--------|--------|
  | `/tmp/env39` | `pip install -c constraints/py3.9.txt -e ".[dev,solver]"` | 0 | `3.7.2` | re-freeze vs 文件 **0 drift** |
  | `/tmp/env311` | `pip install -c constraints/py3.11.txt -e ".[dev,solver]"` | 0 | `3.7.2` | re-freeze vs 文件 **0 drift** |
- 功能 smoke（两环境，casadi 3.7.2）：5-stage CD2 列 `Column(spec).solve()` → `success=True`，`T_top=23.2679` K（env39/env311 一致）。
- 证据：`/tmp/opencode/pm4012/reinstall_env{39,311}.log`、`refreeze_diff_env{39,311}.txt`、`ac8_benchmark.log`、`benchmark_results.json`。

**AC8 首跑（**非同构补充**，保留）**：首次 AC8 在 `.venv`（Python 3.12，**casadi 3.8.0**）运行 →
`3 passed, exit 0, 119.68 s`。该结果**不构成 CI 同构证据**：当时 `benchmark` / `e2e-modelica` 的 install
仍为**无约束** `pip install -e ".[dev,solver]"`，在 3.12 上会浮动 casadi，**违背** D2「三腿统一 3.7.2」意图。
（早前草稿中「无约束 = CI 同构」的推论**错误，已删除**。）该 3.8.0 结果仅作为**非同构补充**保留；
正式同构证据见 §11.8。

### 11.8 D1 细化：benchmark / e2e 浮动 casadi 闭合（2026-09-24 用户验收发现，记录先行）

**触发**：用户验收发现 `benchmark` 与 `e2e-modelica` 两个 job 的 install 未带 `-c` 约束，
在 Python 3.12 上浮动到最新 casadi，**违背** D2「三腿统一 3.7.2」意图。用户指令：**不另问**，立即闭合。

**D1 细化（同文件范围）**：
- `.github/workflows/ci.yml`：`benchmark` 与 `e2e-modelica` 的 install 改为
  `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"`（二者均 Python 3.12 ⇒ 消费 3.12 约束）。
- `tests/test_ci_configuration.py`：**新增不变量**（先 RED 后 GREEN）——benchmark 与 e2e-modelica 的
  editable install 必须含 `-c constraints/ci-3.12.txt`。
- 隔离环境 `/tmp/opencode/pm4012/env312`（真实 Python 3.12 + `-c constraints/ci-3.12.txt`）：
  验证 `casadi==3.7.2` 并**重跑 benchmark**，作为 AC8 的**同构**证据。
- **纠正**：删除「无约束 = CI 同构」错误推论；`.venv`（casadi 3.8.0）首跑降级为**非同构补充**。

**执行结果**：见 §11.9。

### 11.9 D1 细化执行结果（benchmark / e2e casadi 闭合，2026-09-24 追加）

**代码 / 测试（先 RED 后 GREEN）**：
- `.github/workflows/ci.yml`：`benchmark`（L146）与 `e2e-modelica`（L186）install 改为
  `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"`。
- `tests/test_ci_configuration.py` 新增 `test_benchmark_and_e2e_pin_dependencies`：
  - **RED**：`pytest …::test_benchmark_and_e2e_pin_dependencies -q` → **exit 1**
    （`found: ['pip install -e ".[dev,solver]"']`）。证据 `red_d1_constraints.log`。
  - **GREEN**：`pytest tests/test_ci_configuration.py -q` → **exit 0，6 passed**。证据 `green_d1_constraints.log`。

**真实 3.12 CI 约束隔离环境** `/tmp/opencode/pm4012/env312`（Python 3.12.3）：
- `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"` → **exit 0**（81 s）。证据 `env312_install.log`。
- 已装 `casadi==3.7.2`、`numpy==2.4.6`、`pytest==9.0.3`、`ruff==0.15.13`；**与 `ci-3.12.txt` 共享 pin 全部一致**。
- 功能 smoke：5-stage CD2 列 `solve()` → `success=True`，`T_top=23.2679` K（与 env39 / env311 一致）。
- re-freeze 对比 `refreeze_diff_env312.txt`：`ci-3.12.txt` 为**超集**（含 docs / pre-commit 等），
  `[dev,solver]` 闭包为其子集外加 pip-audit 依赖；差异**全部为“仅存在性”**，共享包**无版本漂移**。

**AC8 同构复跑**（env312 ≡ CI `benchmark` job：3.12 + `ci-3.12.txt` → casadi 3.7.2）：
- `pytest tests/benchmark/ --benchmark-enable --override-ini="addopts="` → **exit 0，3 passed，143.53 s**
  （cd2_75 = 0.887 s / isso_3col = 69.55 s / bubble_1000x = 0.158 s）。证据 `ac8_benchmark_env312.log`、`benchmark_results_env312.json`。
- **非同构补充（保留）**：`.venv`（casadi 3.8.0）首跑 `3 passed / 119.68 s`。证据 `ac8_benchmark.log`。

**AC9 wheel clean smoke 完整日志**：`ac9_wheel_smoke.log`（`set -x` 全程）——
`uv build --wheel` 成功 → 纯净 venv 装 wheel + pytest → `smoke OK`（无 casadi，惰性导入成立）→
`tests/test_data_resources.py` **8 passed**；AC9 **exit 0**。

**轻量复验**：`ruff check`（pin 0.15.13）**exit 0**；`ruff format --check` **exit 0**；
`pytest tests/test_optional_solver.py tests/test_ci_configuration.py -q` → **9 passed，exit 0**；
ci.yml YAML 解析通过（benchmark / e2e 均含 `-c constraints/ci-3.12.txt`）。

**未 commit**（HEAD 仍 `49765f1`）。
