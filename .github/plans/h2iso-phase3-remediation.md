# h2iso Phase 3+ Remediation & Hardening

> **Source**: `.github/reviews/full-repo-2025-05-19.md` — 4 🔴 / 11 🟡 / 3 🟢 findings
> **Scope mode**: HOLD — bounded to documented review gaps
> **Branch strategy**: One feature branch per Phase; Phase 3 first (blocks engineering use), Phases 4–6 sequenced after

## 背景与目标

- **问题/需求描述**：h2iso 已完成 L1-VLE + L2-MESH + Phase 2 Flowsheet 求解器（257 tests 全绿，ISS-O 三塔验证通过），但完整审阅暴露：(1) 4 个 🔴 bug 阻塞工程使用；(2) 11 个 🟡 鲁棒性问题影响可靠性；(3) 缺少 ISS-I 内循环验证、多压系统、SRK 完整实现等工程功能；(4) 缺少 property-based / error-path / 性能回归测试
- **目标**：
  - 修复全部 4 个 🔴 阻塞 bug（FlowsheetResult profile 丢失、fsolve 收敛未检查、塔失败静默吞掉、wheel 安装下数据路径崩溃）
  - 加固输入验证与数值鲁棒性（11 个 🟡 issues）
  - 扩展 ISS-I 内循环拓扑配置与验证（依赖 CFEDR 设计组提供数据）
  - 实现 SRK EOS（替换 SRKQuantum 占位符）与多压塔支持
  - 补齐测试金字塔：property-based fuzz、error path、性能回归
- **非目标（不做什么）**：
  - 不实现动态 Modelica 模型（保留 tricys L3 边界）
  - 不实现 He-3/He-4 惰性气体处理（GAP-09 优先级低）
  - 不重构 Phase 1/2 已稳定模块的接口（仅修补 bug）
  - 不引入新外部依赖（除可选 SRK 求解器外）
- **已有代码/流程复用分析**：
  - `h2iso.flowsheet.*`：**复用**（仅修补 BG-01/BG-03/BG-07）
  - `h2iso.equilibrator.exchange`：**复用**（仅修补 BG-02）
  - `h2iso.vle.mixing.rachford_rice`：**复用**（仅修补 BG-04）
  - `h2iso.mesh.column._compute_flows`：**复用**（仅添加输入验证）
  - 现有 `data/parameters/*.json`：**复用**（迁移到 `src/h2iso/data/parameters/`）
  - Wang 2022 fixtures：**复用**（作为回归基线）
  - hypothesis 已在 dev deps：**复用**（Phase 6 启用）

## 技术方案

- **方案概述**：分 4 个 Phase 实施。Phase 3 (P0) 必须先合并，否则后续 Phase 的测试基线不可信；Phase 4 (P1) 加固后才能开放给外部用户；Phase 5/6 (P2/P3) 按业务优先级排
- **关键设计决策**：
  1. **数据路径用 `importlib.resources.files()`**（Py 3.9+ stdlib），将 `data/parameters/` 物理移入 `src/h2iso/data/parameters/`，`pyproject.toml` 改为 `package-data = { h2iso = ["data/parameters/*.json", "data/schemas/*.json"] }`
  2. **塔求解失败处理**：从 `except RuntimeError: pass` 改为记录到 `FlowsheetResult.unit_failures: dict[str, str]`，并向上传播，调用者可决定是否继续；保留"继续迭代用陈旧值"的选项但必须显式开启
  3. **ISS-I 拓扑配置外置**：新建 `tests/fixtures/iss_i/`，需 CFEDR 提供配置数据后实施；Task 5.1 在数据到位前 `[BLOCKED]`
  4. **SRK 实现策略**：采用 cubic EOS 标准求解（Z³ + αZ² + βZ + γ = 0），mixing rule 用 vdW + kij；不破坏 `EOS` 抽象基类
  5. **多压支持**：`ColumnSpec.pressure` 已是 per-column 字段，但流股压力变化处理（throttle valve / pump）需新增 `PressureChangerUnit`
  6. **测试策略**：每个 bug 修复必须先写失败测试再修代码（TDD）；property tests 用 hypothesis @given 覆盖组成单纯形约束
- **影响范围**：
  - Phase 3: `flowsheet/solver.py`, `flowsheet/unit.py`, `flowsheet/stream.py`, `equilibrator/exchange.py`, `vle/mixing.py`, 全部 `_DATA_DIR` 引用文件 (7), `pyproject.toml`
  - Phase 4: `mesh/column.py`, `mesh/continuation.py`, `mesh/enthalpy.py`, `flowsheet/unit.py`, `flowsheet/solver.py`
  - Phase 5: `flowsheet/unit.py` (新增 PressureChangerUnit), `vle/eos.py` (SRK 完整实现), 新增 `tests/fixtures/iss_i/`
  - Phase 6: 新增 `tests/property/`, `tests/error_paths/`, `tests/benchmark/`

## Error & Rescue Map

| 代码路径/操作 | 可能的失败 | 错误类型 | 已处理？ | 处理方式 | 用户可见行为 |
|--------------|-----------|---------|---------|---------|------------|
| 数据迁移后旧路径残留 | import h2iso 时 FileNotFoundError | ImportError | Y | T3.4 一次性更新全部 7 处 `_DATA_DIR`，CI 在 wheel + editable 两种安装下都跑测试 | 明确 import 失败信息 |
| `column_results` 修复后旧测试假设 None | 测试断言失败 | AssertionError | Y | T3.1 同步更新 `test_isso_*.py` 中已有断言 | 测试报告指出修改位置 |
| Phase 4 输入验证过严导致回归 | 现有 fixture/test 失败 | ValueError | Y | T4.x 先跑全量测试，对触发的合法用例放宽边界 | 回归测试覆盖 |
| Phase 5 SRK 不收敛 | cubic 求根失败 | RuntimeError | Y | 提供 fallback 到 IdealVLE + warning，并在结果中标记 | warning 显示 |
| Phase 5 ISS-I 数据未到位 | Task 5.1 blocked | (none) | Y | Task 标记 `[BLOCKED ON INPUT]`，Phase 5 其他 task 不受影响 | 计划文档显式说明 |
| importlib.resources 在某些打包模式下行为差异 | 资源路径返回 MultiplexedPath | TypeError | Y | T3.4 统一用 `as_file()` context manager，避免直接传 Path | — |

## 执行计划

### Phase 3: P0 Critical Bug Fixes（阻塞工程使用）

#### ✅ Task 3.1: 修复 FlowsheetResult.column_results 数据丢失 (BG-01)
- **目标**：调用者能从 `FlowsheetResult.column_results[name]` 获取完整 `ColumnResult`（T_profile、x_profile、y_profile）
- **依赖**：无
- **修改内容**：
  - 文件 `src/h2iso/flowsheet/unit.py`：在 `ColumnUnit.solve()` 末尾添加 `self._last_result = result`（result 来自 `Column.solve()` / `ContinuationSolver.solve()`）
  - 文件 `src/h2iso/flowsheet/solver.py`（`_execute_sequence` 函数附近，原 L284）：删除 `unit._last_result = None` 这一行；保留 `if isinstance(unit, ColumnUnit)` 的检查逻辑结构
  - 文件 `tests/test_flowsheet/test_isso_full.py`：添加测试断言 `result.column_results["CD1"] is not None and result.column_results["CD1"].T_profile.shape == (60,)`
- **修改边界**：不修改 `_execute_sequence` 中的异常处理逻辑（属于 T3.3）；不修改 `FlowsheetResult` dataclass 定义
- **测试要求**：
  - `pytest tests/test_flowsheet/test_isso_full.py -v` — 新增断言通过
  - 全量回归：`pytest --tb=short` — 257+ tests 通过
- **验收标准**：
  - ✅ `FlowsheetResult.column_results["CD1"].T_profile` 返回 length-60 ndarray
  - ✅ `result.column_results["CD2"].x_profile.shape == (70, 6)`
  - ✅ 全量测试无回归
- **潜在风险**：`ContinuationSolver` 返回的 result 类型可能与 `Column.solve()` 不同——需检查并统一为 `ColumnResult`

#### ✅ Task 3.2: 检查 fsolve 收敛标志 (BG-02)
- **目标**：`equilibrium_composition()` 在 fsolve 不收敛时显式 raise，不再返回垃圾值
- **依赖**：无
- **修改内容**：
  - 文件 `src/h2iso/equilibrator/exchange.py`（`equilibrium_composition` 函数附近，L157-171）：将 `sol = fsolve(...)` 改为 `sol, info, ier, mesg = fsolve(...)`；添加 `if ier != 1: raise RuntimeError(f"Equilibrium solve failed (ier={ier}): {mesg}")`
  - 文件 `tests/test_equilibrator/test_exchange.py`：添加失败场景测试（如极端 atom fractions 触发不收敛后 pytest.raises(RuntimeError)）
- **修改边界**：不修改 `keq()`、`atom_fractions()`；不修改 `EquilibratorUnit.solve()` 上游调用
- **测试要求**：
  - `pytest tests/test_equilibrator/test_exchange.py -v` 通过
  - 全量回归通过
- **验收标准**：
  - ✅ 正常输入下结果与修复前一致（精度 < 1e-10）
  - ✅ 构造不收敛场景能稳定触发 RuntimeError，错误消息含 ier 和 mesg
- **潜在风险**：scipy 不同版本 fsolve 返回顺序一致——经验证 ≥1.0 稳定

#### ✅ Task 3.3: 塔求解失败不再静默吞掉 (BG-03)
- **目标**：`SequentialModularSolver` 在塔求解失败时记录到 `FlowsheetResult.unit_failures`，并按策略决定是否继续
- **依赖**：T3.1（避免对 `_execute_sequence` 的合并冲突，T3.1 先合并）
- **修改内容**：
  - 文件 `src/h2iso/flowsheet/solver.py`：
    - `FlowsheetResult` dataclass 新增字段：`unit_failures: dict[str, str] = field(default_factory=dict)`
    - `SequentialModularSolver.__init__` 新增参数：`on_unit_failure: Literal["raise", "skip", "stale"] = "raise"`（默认 raise，向后兼容时可在 ISS-O fixture 中改为 "stale" 保留旧行为）
    - `_execute_sequence` 的 `except RuntimeError as e` 分支：根据 `on_unit_failure` 策略选择 raise / break / pass，并写入 `self._unit_failures[unit.name] = str(e)`
  - 文件 `tests/test_flowsheet/test_solver.py`：新增 `test_on_unit_failure_raise`、`test_on_unit_failure_stale` 两个测试
- **修改边界**：不修改 T3.1 添加的 `_last_result` 赋值；不修改 Wegstein 算法逻辑
- **测试要求**：
  - `pytest tests/test_flowsheet/test_solver.py -v` 通过
  - 全量回归通过（ISS-O fixture 需明确设 `on_unit_failure="stale"` 才能保留旧行为，否则改为 raise）
- **验收标准**：
  - ✅ 默认 `on_unit_failure="raise"` 时塔失败立即抛出
  - ✅ `on_unit_failure="stale"` 时记录失败但继续，`FlowsheetResult.unit_failures` 含失败塔名
  - ✅ `on_unit_failure="skip"` 时跳过该塔的当前迭代
- **潜在风险**：现有 ISS-O 测试依赖旧的静默行为——需逐个检查并显式设置策略

#### ✅ Task 3.4: `_DATA_DIR` 迁移到 importlib.resources (CQ-01)
- **目标**：h2iso 通过 `pip install h2iso`（非 editable）安装后能正常加载所有参数 JSON
- **依赖**：无
- **修改内容**：
  - 物理移动：`data/parameters/*.json` → `src/h2iso/data/parameters/*.json`；`data/schemas/*.json` → `src/h2iso/data/schemas/*.json`（用 `git mv`）
  - 新建 `src/h2iso/_data.py`：提供 `data_path(category: str, filename: str) -> Path` 工具函数，内部用 `importlib.resources.files("h2iso").joinpath("data", category, filename)`，配合 `as_file()` context manager 处理 wheel 中的 zipimport 情况
  - 修改 7 个引用 `_DATA_DIR` 的文件，统一改为调用 `from h2iso._data import data_path; with data_path("parameters", "species.json") as p: ...`：
    - `src/h2iso/species.py`
    - `src/h2iso/vle/mixing.py`
    - `src/h2iso/vle/souers.py`
    - `src/h2iso/vle/quantum.py`
    - `src/h2iso/equilibrator/exchange.py`
    - `src/h2iso/mesh/enthalpy.py`
    - `src/h2iso/codegen/modelica_records.py`
  - 修改 `pyproject.toml`：`[tool.setuptools.package-data]` 改为 `h2iso = ["data/parameters/*.json", "data/schemas/*.json"]`；删除旧的 `"../data/parameters/*.json"` 路径
  - 修改 `.github/workflows/ci.yml`：增加一个 job `test-wheel`，先 `pip wheel . -w dist/`，再在干净 venv 中 `pip install dist/*.whl`，然后 `cd /tmp && python -c "import h2iso; ..."` 跑核心 smoke test
  - 新增 `tests/test_data_resources.py`：验证 6 个 JSON 文件均可通过 `data_path()` 正常加载
- **修改边界**：不修改任何 JSON 文件内容；不修改求解器算法
- **测试要求**：
  - `pytest tests/test_data_resources.py -v` 通过
  - `python -m build && pip install dist/h2iso-*.whl` 在干净 venv 中可 import 并跑通 ISS-O 验证（手动 smoke 验证）
  - 全量回归通过
- **验收标准**：
  - ✅ Editable install (`pip install -e .`) 下全部测试通过
  - ✅ Wheel install 在干净 venv 下 `python -c "from h2iso.vle import bubble_pressure; ..."` 不报 FileNotFoundError
  - ✅ CI 新增 test-wheel job 通过
- **潜在风险**：`importlib.resources.files()` 在 Py 3.9 与 3.10+ 的行为有细微差异——必须用 `as_file()` 包装，确保 zipimport 兼容

### Phase 4: P1 Robustness Hardening

#### ✅ Task 4.1: Stream/ColumnSpec 输入验证 (CQ-02 / CQ-03 / CQ-04 / CQ-05)
- **目标**：所有边界外输入在构造时立即报错，不让畸形数据进入求解器
- **依赖**：Phase 3 全部完成
- **修改内容**：
  - 文件 `src/h2iso/flowsheet/stream.py`（`Stream.__post_init__` 附近）：添加 `_validate_composition()` 检查 `composition >= -1e-12` 和 `abs(sum - 1.0) < 1e-9`，违反则 raise ValueError
  - 文件 `src/h2iso/mesh/column.py`（`Column.__init__` 或 `ColumnSpec.__post_init__` 附近）：
    - `n_stages >= 2` 检查（否则 IndexError）
    - `0.0 < distillate_to_feed < 1.0` 检查
  - 文件 `src/h2iso/flowsheet/unit.py`（`EquilibratorUnit.solve`）：在调用 `equilibrium_composition` 前检查 `T_eq > 0`
  - 文件 `tests/test_flowsheet/test_stream.py`、`tests/test_mesh/test_column.py`：新增对应 pytest.raises 测试
- **修改边界**：不修改算法逻辑；仅在入口添加 guard
- **测试要求**：全量回归通过；新增 ≥6 个 pytest.raises 测试通过
- **验收标准**：
  - ✅ `Stream(flow=1, composition=[-0.1, 1.1, 0, 0, 0, 0], ...)` 立即 ValueError
  - ✅ `ColumnSpec(n_stages=1, ...)` 立即 ValueError
  - ✅ `ColumnSpec(distillate_to_feed=1.5, ...)` 立即 ValueError
  - ✅ `EquilibratorUnit(temperature=0)` 在 solve 时 ValueError
- **潜在风险**：现有 fixture 中可能有未严格归一化的组成——需检查并修正

#### ✅ Task 4.2: 数值安全加固 (CQ-06 / CQ-07 / BG-04)
- **目标**：消除已知 NaN/Inf 传播路径
- **依赖**：T4.1
- **修改内容**：
  - 文件 `src/h2iso/vle/mixing.py`：
    - `kvalue` 计算后添加 `if np.any(K <= 0): raise ValueError(...)`
    - `rachford_rice` 的 `V_min >= V_max` 分支改为 raise ValueError，不再 fallback `0.5`
  - 文件 `src/h2iso/mesh/enthalpy.py`：在 `np.log(T / T_REF)` 前添加 `if np.any(np.asarray(T) <= 0): raise ValueError(...)`
  - 新增 `tests/test_vle/test_error_paths.py`：构造 K=0、V 括号失败等场景，断言 ValueError
- **修改边界**：不修改正常路径数值结果
- **测试要求**：全量回归通过；新增错误路径测试通过
- **验收标准**：
  - ✅ K=0 时 raise ValueError
  - ✅ Rachford-Rice 括号无效时 raise ValueError，不再静默返回 0.5
  - ✅ T<=0 时 enthalpy 计算 raise ValueError

#### ✅ Task 4.3: Wegstein 与 Continuation 数值稳定性 (BG-05 / CQ-08 / BG-06 / BG-07)
- **目标**：修复 Wegstein 破坏组成单纯形、continuation 扰动后不归一化、method 参数无校验等问题
- **依赖**：T4.1
- **修改内容**：
  - 文件 `src/h2iso/flowsheet/solver.py`：
    - `__init__`: 添加 `if self.method not in ("direct", "wegstein"): raise ValueError(...)`
    - `_wegstein_update`: 对组成块（每 6 元素）只更新前 5 个独立分量，第 6 个用 `1 - sum(前5)` 计算；temperature/flow 不受影响
  - 文件 `src/h2iso/mesh/continuation.py`（`_continue_N` 附近，L164）：扰动后按 6 元素块归一化组成
  - 文件 `src/h2iso/flowsheet/unit.py`：`ColumnUnit.solve` 中 continuation 分支处理 `spec.feeds is not None` 但 `base_feeds is None` 的情况
  - 新增 `tests/test_flowsheet/test_wegstein_simplex.py`：用 hypothesis 验证 Wegstein 更新后组成始终满足单纯形约束
- **修改边界**：不修改 q 范围 [-5, 0.9]；不修改 tear stream 检测逻辑
- **测试要求**：全量回归通过；新增 property test 通过
- **验收标准**：
  - ✅ `SequentialModularSolver(method="Wegstein")`（大小写错误）raise ValueError
  - ✅ Wegstein 100 次迭代后所有 tear stream 组成满足 `abs(sum-1) < 1e-12` 且非负
  - ✅ ISS-O 收敛迭代数不增加（≤ 4）

### Phase 5: P2 Functional Extensions

#### Task 5.1: ISS-I 内循环拓扑配置与验证 [BLOCKED ON INPUT]
- **目标**：建立 ISS-I（内燃料循环 5-7 塔）拓扑配置文件并通过 Wang/参考数据验证
- **依赖**：Phase 3+4 完成；**CFEDR 设计组提供 ISS-I 配置数据（塔数、R、D/F、压力、互联关系）**
- **修改内容**：
  - 新建 `tests/fixtures/iss_i/iss_i_config.json`：5-7 塔配置（含 tear streams）
  - 新建 `tests/fixtures/iss_i/iss_i_reference.json`：参考结果（来自 Aspen/Wang 文献）
  - 新建 `tests/test_flowsheet/test_iss_i.py`：端到端求解 + 与参考值对比
  - 新建 `docs/validation/iss_i_report.md`：验证报告
- **修改边界**：不修改求解器算法
- **测试要求**：
  - `pytest tests/test_flowsheet/test_iss_i.py -v` 通过
- **验收标准**：
  - ✅ ISS-I 求解收敛（迭代数 ≤ 10）
  - ✅ 产品组成相对误差 < 5%
  - ✅ 温度偏差 < 2 K
- **潜在风险**：BLOCKED — 数据未到位前该 Task 不启动；可在用户/CFEDR 提供后并行实施 T5.2/T5.3

#### ✅ Task 5.2: 多压系统支持 — PressureChangerUnit
- **目标**：支持流股压力变化（阀门 throttle、泵 pump、压缩机 compressor），允许塔间不同压力级联
- **依赖**：Phase 3+4 完成
- **修改内容**：
  - 文件 `src/h2iso/flowsheet/unit.py`：新增 `PressureChangerUnit(UnitOp)`，参数 `target_pressure: float`、`mode: Literal["throttle", "pump", "compressor"]`；throttle 等焓、pump 等熵
  - 文件 `src/h2iso/flowsheet/schema.py`：JSON schema 添加 `pressure_changer` 节点类型
  - 文件 `data/schemas/flowsheet_v1.json`：相应 schema 扩展（或升级 v2）
  - 新增 `tests/test_flowsheet/test_pressure_changer.py`：throttle 等焓验证（与 enthalpy.py 配合）
- **修改边界**：不修改现有 ColumnUnit/EquilibratorUnit 行为
- **测试要求**：新增 ≥3 个 unit test 通过；schema 验证通过
- **验收标准**：
  - ✅ throttle 压力下降后温度变化与 Joule-Thomson 系数符号一致
  - ✅ JSON 配置含 pressure_changer 可被 schema 验证通过
  - ✅ 嵌入 ISS-O 流程后求解仍收敛

#### ✅ Task 5.3: SRK EOS 完整实现 (GAP-02 / DR-12)
- **目标**：替换 `SRKQuantum` 占位符，实现完整 SRK + 量子修正 alpha 函数
- **依赖**：Phase 3+4 完成
- **修改内容**：
  - 文件 `src/h2iso/vle/eos.py`：`SRKQuantum.kvalue` 实现 cubic Z 求解（Cardano 或 numpy.roots）、fugacity coefficient via SRK departure function、vdW 混合规则 + kij
  - 文件 `src/h2iso/vle/quantum.py`：alpha 函数添加 Feynman-Hibbs 量子修正项
  - 文件 `tests/test_vle/test_srk.py`：与 IdealVLE 对比在低压趋于一致；与文献 SRK 结果对比
  - 文件 `docs/api/vle.md`：更新文档说明 SRK 现在是真实实现
- **修改边界**：不修改 `IdealVLE`；不修改 BIP 数值
- **测试要求**：低压下 SRK 与 IdealVLE 相对偏差 < 1%；新增测试通过
- **验收标准**：
  - ✅ P < 50 kPa 下 SRK 与 IdealVLE 偏差 < 1%
  - ✅ P > 500 kPa 下 SRK 显示出非理想行为（K 值与 IdealVLE 偏差 > 5%）
  - ✅ 与 DWSIM SRK 结果对比偏差 < 2%

### Phase 6: P3 Test Pyramid Completion

#### ✅ Task 6.1: Property-based testing (hypothesis)
- **目标**：用 hypothesis 覆盖关键不变性，发现 edge case
- **依赖**：Phase 3+4 完成（输入验证就位后 property test 才有意义）
- **修改内容**：
  - 新建 `tests/property/test_vle_invariants.py`：
    - 组成归一化：随机生成 (T, x) → bubble_pressure → y 满足 `abs(sum(y)-1) < 1e-9`
    - 单调性：随机 x，T 增加 → bubble_P 增加
  - 新建 `tests/property/test_mass_balance.py`：
    - 任意 ColumnSpec → result 满足 F_in*z = D*x_top + B*x_bot（≤ 1% 误差）
  - 新建 `tests/property/test_equilibrium_invariants.py`：原子守恒（H, D, T 总原子数前后一致）
- **修改边界**：仅添加测试；不修改 src/
- **测试要求**：`pytest tests/property/ -v --hypothesis-seed=0` 通过；至少 100 examples per test
- **验收标准**：
  - ✅ 至少 3 个 property tests 通过
  - ✅ 任何发现的反例必须修复或文档化为已知局限
- **潜在风险**：hypothesis 可能发现真实 bug——需预算时间修复

#### ✅ Task 6.2: Error path coverage
- **目标**：系统化测试求解器在异常输入下的行为
- **依赖**：Phase 3+4 完成
- **修改内容**：
  - 新建 `tests/error_paths/test_solver_failures.py`：
    - 不可行 D/F 配置 → 明确错误
    - 极端 R（0 或 1e6）→ IPOPT 失败时的行为
    - 畸形 JSON config → schema 验证错误
  - 新建 `tests/error_paths/test_invalid_inputs.py`：覆盖 T4.1/T4.2 验证规则的边界
- **修改边界**：仅添加测试
- **测试要求**：新增 ≥10 个错误路径测试通过
- **验收标准**：
  - ✅ 每个 raise ValueError/RuntimeError 路径至少有一个测试
  - ✅ 错误消息中含可调试信息（变量名、违规值）

#### Task 6.3: Performance regression benchmarks
- **目标**：建立性能基线，CI 检测显著回归（> 50% 变慢）
- **依赖**：Phase 3+4 完成
- **修改内容**：
  - 新建 `tests/benchmark/test_performance.py`：使用 `pytest-benchmark`（添加到 dev deps）记录：
    - CD2 75-plate 求解时间（baseline ~10s）
    - ISS-O 三塔求解时间（baseline ~30s）
    - VLE bubble_pressure 1000 次（baseline < 1s）
  - 修改 `.github/workflows/ci.yml`：新增 benchmark job（仅 main 分支跑，结果存 artifacts）
  - 新建 `docs/validation/performance_baseline.md`：记录基线数值与硬件
- **修改边界**：不修改求解器算法
- **测试要求**：benchmark 跑通；CI artifact 上传成功
- **验收标准**：
  - ✅ benchmark 输出含统计（mean、median、std）
  - ✅ 基线数据记录到文档
- **潜在风险**：CI runner 性能波动——使用相对值（vs 上次 main）而非绝对阈值

#### Task 6.4: End-to-end h2iso → tricys → simulate 测试 (GAP-10)
- **目标**：codegen 生成的 .mo 文件能被 OMC 编译；init_from_h2iso.py 生成的 .mos 能在 tricys 中跑通仿真
- **依赖**：T5.1, T5.2 完成（如果集成 ISS-I）；OMC 1.23+ 可用环境
- **修改内容**：
  - 新建 `tests/e2e/test_modelica_compile.py`：用 `omc -s` 或 OMPython 编译生成的 `.mo` 文件
  - 新建 `tests/e2e/test_tricys_init.sh`：脚本化端到端测试（h2iso solve → .mos → omc simulate → 提取结果）
  - 修改 `.github/workflows/ci.yml`：新增 e2e job（可选触发，因 OMC 安装较重）
- **修改边界**：不修改 codegen 输出格式（除非编译失败需修复）
- **测试要求**：所有 6 个 species record .mo 和 6 个 pvap function .mo 编译通过
- **验收标准**：
  - ✅ OMC 编译生成的 .mo 无语法错误
  - ✅ tricys 模型加载 .mos 后仿真完成
- **潜在风险**：OMC 环境配置复杂——可降级为 docker-based CI

## Execution Wave

| Wave | 可并行 Task | 依赖已完成 |
|------|------------|------------|
| W1 | T3.1, T3.2, T3.4 | — |
| W2 | T3.3 | W1 (T3.1) |
| W3 | T4.1 | W2 (Phase 3 全部) |
| W4 | T4.2, T4.3 | W3 |
| W5 | T5.2, T5.3, T6.1, T6.2, T6.3 | W4 (Phase 4 全部) |
| W6 | T5.1 (BLOCKED until data), T6.4 | W5 + ISS-I data |

> Task Executor 按 Wave 顺序实施：每个 Task 单独 commit；每个 Phase 完成后 push + 可选发起 PR。

## 回归检查清单

- [ ] Phase 3 完成后：全部 257 tests 通过 + 4 个 🔴 bug 修复测试通过
- [ ] Phase 4 完成后：全部测试 + 新增 ≥10 个验证测试通过
- [ ] Phase 5 完成后：ISS-I 验证报告生成（如数据到位）；SRK 与 DWSIM 对比 < 2%
- [ ] Phase 6 完成后：property tests 至少 100 examples 不发现新反例
- [ ] 每个 Phase：`ruff check src/ tests/` 无错误
- [ ] 每个 Phase：CI 全部 job 绿（含新增 test-wheel job）
- [ ] 每个 Phase：文档同步更新（CHANGELOG / docs/）

## 审查日志

| 轮次 | 聚焦 | 发现问题数 | 已修正 | 剩余 |
|------|------|-----------|--------|------|
| R1 | 结构完整性 | 1 (T3.x 缺 `依赖` 字段) | 1 | 0 |
| R1.5 | 外部引用事实核查 | 0 (`solver.py:284`, `exchange.py:171`, `mixing.py:233`, `stream.py:37` 全部已 grep 确认) | 0 | 0 |
| R2 | 可执行性（含脚本干跑） | 1 (importlib.resources Py 3.9 兼容性) — 已确认 stdlib 含 files() API | 1 | 0 |
| R3 | 风险与边缘（含跨轮一致性） | 1 (T3.1 与 T3.3 都改 `_execute_sequence`) — 已添加显式边界约定 T3.1 先合并 | 1 | 0 |
| **终止** | **T1 — 收敛终止** | | | **0** |

### Completion Summary

| 维度 | 结果 |
|------|------|
| 背景与目标 | 完整（含非目标） |
| 技术方案 | 完整（含 6 个关键设计决策） |
| Error & Rescue Map | 6 条关键失败路径，全部已处理 |
| 执行计划 | 4 Phases / 12 Tasks |
| Execution Wave | 6 waves，含 BLOCKED 标注 |
| 回归检查清单 | 7 项（含 wheel install / CI） |
| 已知局限 | T5.1 BLOCKED ON INPUT（CFEDR ISS-I 数据）；T6.4 依赖 OMC 环境 |

## Pre-Delivery Audit (Level: L1-Lite)

| § | Check | Status | Note |
|---|-------|--------|------|
| 1 | Unit consistency | ✅ PASS | 所有物理量（Pa、K、mol/h）保持 Phase 1/2 约定 |

Auditor: Plan Architect | Date: 2026-05-19
