# h2iso 构建方案与执行计划

## 背景与目标

- **问题/需求描述**：tricys 多保真精馏架构中，L1（VLE 物性内核）和 L2（CasADi 稳态 MESH 求解器）需要一个独立的 Python 库来承载。该库需要与 tricys 的 OMPython 依赖隔离，同时具备独立发表价值。
- **根因分析**：氢同位素（H₂/HD/HT/D₂/DT/T₂）低温精馏的核心难点在于：(1) VLE 参数需自建和验证（Souers 关联式 + 量子修正）；(2) 相对挥发度接近 1，MESH 方程对初值高度敏感；(3) 60-100 理论板导致强耦合大规模非线性系统。现有开源工具（DWSIM）仅适用于 ≤15 板轻量验证，无法覆盖工程需求。
- **目标**：
  - 建立开源氢同位素低温热力学 Python 库 `h2iso`
  - 实现 L1-VLE 物性内核（Souers 蒸汽压、量子修正、K-value、BIP/kij）
  - 实现 L2-CasADi 稳态 MESH 高板数精馏求解器（支持 15-100 理论板）
  - 与 Wang 2022 / DWSIM / Aspen 基准交叉验证
  - 输出 Modelica 初始化 profile，供 tricys L3 层使用
- **非目标（不做什么）**：
  - 不实现 Modelica 动态塔模型（那是 tricys L3 层的工作）— 只输出初值
  - 不深改 DWSIM C# 核心 — DWSIM 仅作为外部 benchmark 参考
  - 不实现完整的催化平衡器动力学（Phase 1 只做平衡组成求解）— 动力学留到后续
  - 不实现 GUI 或 Web 前端 — 纯 Python 库 + CLI
  - 不做 ortho/para-H₂ 的完整量子统计力学模型 — 用 Souers 经验关联式 + 修正因子
- **已有代码/流程复用分析**：
  - `tricys` branch `feature/dwsim-equivalence-verification` 上的 Wang 2022 benchmark fixtures (JSON): **复用**（直接迁移 4 个 fixture 文件）
  - `tricys` DWSIM 脚本 (`script/dwsim/`): **不复用**（DWSIM 仍留在 tricys 内，h2iso 只消费其输出结果）
  - `distillation_roadmap.md` Phase 1/2 任务表: **复用**（作为 h2iso 的规范输入）

## 技术方案

- **方案概述**：h2iso 采用 `src/` layout 的纯 Python 库结构，核心依赖为 `numpy + scipy + casadi`。分两个主要 package：`h2iso.vle`（L1 物性）和 `h2iso.mesh`（L2 求解器）。参数数据存储为 JSON 文件（单一数据源），未来可自动生成 Modelica `.mo` 文件。
- **关键设计决策**：
  1. **src layout** — 避免 import 歧义，符合现代 Python packaging 实践
  2. **CasADi 符号化 VLE** — VLE 函数同时支持 numpy (数值) 和 casadi.SX (符号) 输入，使 MESH 求解器能直接嵌入 VLE 方程获得精确 Jacobian
  3. **参数即数据** — 所有物性参数存入 `data/parameters/*.json`，Python 代码读取，未来 codegen 脚本生成 Modelica record
  4. **分级 continuation** — MESH 求解从短塔 warm start 到长塔，避免 cold-start 失败
  5. **pytest + hypothesis** — 物性函数用 property-based testing 确保边界安全（无 NaN/负值/越界）
- **影响范围**：仅 h2iso repo 内部。与 tricys 的集成通过 `pip install h2iso` 或 editable install 实现，不修改 tricys 源码。

## Error & Rescue Map（关键失败路径映射）

| 代码路径/操作 | 可能的失败 | 错误类型 | 已处理？ | 处理方式 | 用户可见行为 |
|-------------|-----------|---------|---------|---------|------------|
| `vle.bubble_point(T, x)` 组成数组含负值 | 非物理输入 | ValueError | Y | 输入校验 + 明确 raise | 错误消息指出哪个组分为负 |
| `vle.souers_pvap(T)` T 超出适用范围 (<14K 或 >35K) | 外推失真 | 无静默错误 | Y | 范围检查 + UserWarning | warning 提示外推 |
| `mesh.Column.solve()` IPOPT 不收敛 | NLP infeasible | SolverError | Y | 返回 ConvergenceResult(success=False, diagnostics=...) | 不 raise，返回诊断信息 |
| `mesh.Column.solve()` continuation 中间步失败 | warm-start chain 断裂 | SolverError | Y | 回退到上一个成功点 + 缩小步长 | 日志记录回退点 |
| `codegen.export_modelica()` 模板文件缺失 | FileNotFoundError | IOError | Y | 检查 template 存在性 | 明确错误消息 |
| `casadi.nlpsol` CasADi 未安装 | ImportError | ImportError | Y | lazy import + 友好提示 | "pip install h2iso[solver]" |

## 执行计划

### Phase 0: Repo 初始化与骨架

#### ✅ Task 0.1: 项目基础结构
- **目标**：建立 h2iso 的 Python 包骨架、CI、文档框架
- **依赖**：无
- **修改内容**：
  - 创建 `pyproject.toml`（metadata、dependencies、optional-dependencies）
  - 创建 `src/h2iso/__init__.py`（版本号、顶层 import）
  - 创建 `src/h2iso/species.py`（6 species registry：H₂/HD/HT/D₂/DT/T₂）
  - 创建 `data/parameters/species.json`（摩尔质量、原子组成、Tc/Pc/omega）
  - 创建 `tests/conftest.py`（共用 fixtures）
  - 创建 `.gitignore`、`LICENSE`（MIT）、`README.md`
  - 创建 `.github/workflows/ci.yml`（pytest + ruff）
- **修改边界**：不创建任何 VLE/MESH 实现代码，仅骨架
- **测试要求**：
  - `pip install -e .` 成功
  - `python -c "import h2iso; print(h2iso.__version__)"` 输出版本号
  - `pytest tests/ -x` 通过（空测试或 species 测试）
- **验收标准**：
  - ✅ `pip install -e ".[dev]"` 无错误
  - ✅ species registry 包含 6 种组分，摩尔质量与 IUPAC 一致
  - ✅ ruff check 通过，无 lint 错误
- **潜在风险**：CasADi wheel 在某些 Linux 发行版上安装复杂 → 设为 optional dependency `[solver]`

#### ✅ Task 0.2: 迁移 Wang 2022 benchmark fixtures
- **目标**：从 tricys 迁移 Wang 2022 benchmark 数据作为 h2iso 的验证基准
- **依赖**：T0.1
- **修改内容**：
  - 复制 `tricys` branch 上的 4 个 fixture JSON 到 `tests/fixtures/wang2022/`
  - 创建 `tests/fixtures/README.md` 说明数据来源和引用信息
- **修改边界**：不修改 tricys repo 中的文件
- **测试要求**：
  - `python -c "import json; json.load(open('tests/fixtures/wang2022/wang2022_issi_cd2.json'))"` 成功
- **验收标准**：
  - ✅ 4 个 fixture 文件完整复制，JSON 有效
  - ✅ README 标注 DOI、表号、数据版本
- **潜在风险**：无

---

### Phase 1: L1-VLE 氢同位素物性内核

#### Task 1.1: Souers 蒸汽压关联式
- **目标**：实现 H₂/HD/HT/D₂/DT/T₂ 的纯组分蒸汽压函数（基于 Souers UCRL-52628）
- **依赖**：T0.1
- **修改内容**：
  - 文件 `data/parameters/vapor_pressure.json`：6 组分的 Antoine/PLXANT 参数 + 适用温区 + 来源标注
  - 文件 `src/h2iso/vle/souers.py`：
    - `pvap(T, species) -> float/ndarray`：纯组分蒸汽压 (Pa)
    - `dpvap_dT(T, species) -> float/ndarray`：温度导数（Clausius-Clapeyron 用）
    - 支持 numpy 数组和 casadi.SX 符号输入（通过 duck typing 或 backend dispatch）
  - 文件 `src/h2iso/vle/__init__.py`：模块入口
- **修改边界**：不实现混合物 VLE，不实现量子修正（T1.2 做）
- **测试要求**：
  - `pytest tests/test_vle/test_souers.py -v`
  - 测试内容：(1) 每个组分在正常沸点返回 101325 Pa ± 50 Pa；(2) T 范围边界返回 warning 不 crash；(3) 与 Souers 表格数据逐点偏差 < 0.1%；(4) CasADi SX 模式能求导
- **验收标准**：
  - ✅ 6 组分蒸汽压在 14-33 K 范围内相对偏差 < 0.1%（对 Souers 原始数据）
  - ✅ 正常沸点（1 atm）温度与文献值偏差 < 0.05 K
  - ✅ CasADi jacobian 可计算且非零
  - ✅ 每个参数标注来源（Souers table N, page M）
- **潜在风险**：Souers 原始参数可能是 log10 而非 ln 基 → 实现时明确标注对数底；部分虚构组分（HD/HT/DT）参数稀疏，需混合文献源

#### Task 1.2: 量子修正与 EOS 框架
- **目标**：在经典蒸汽压基础上加入量子效应修正，建立可插拔 EOS 架构
- **依赖**：T1.1
- **修改内容**：
  - 文件 `src/h2iso/vle/quantum.py`：
    - `quantum_correction(T, species) -> float`：de Boer 量子参数 Λ*，Feynman-Hibbs effective potential 修正
    - `fugacity_correction(T, P, species) -> float`：气相偏离理想因子
  - 文件 `src/h2iso/vle/eos.py`：
    - `EOS` 抽象基类（`fugacity_coeff(T, P, x)`, `activity_coeff(T, P, x)`）
    - `IdealVLE(EOS)`：Raoult 定律 K = Psat/P
    - `SRKModified(EOS)`：SRK + 量子修正 α(T) 函数
  - 文件 `data/parameters/quantum.json`：de Boer Λ* 参数、Feynman-Hibbs 系数、源文献
- **修改边界**：不实现 BIP/kij 混合规则（T1.3 做），不实现 ortho/para 分别建模（标注为 future work）
- **测试要求**：
  - `pytest tests/test_vle/test_quantum.py`
  - 验证：H₂ 在 20 K 下 fugacity_correction 偏离 1.0 约 5-15%（量子效应显著区域）；D₂/T₂ 修正量依次减小（质量越大量子效应越弱）
- **验收标准**：
  - ✅ H₂ 量子修正在 20 K 使 Psat 偏移 > 3%（相对经典值）
  - ✅ 同温度下修正幅度排序：H₂ > HD > D₂ > HT > DT > T₂
  - ✅ 高温极限 (>40 K) 修正趋于 0
  - ✅ CasADi 兼容
- **潜在风险**：Feynman-Hibbs 在极低温（<15 K）可能不够精确 → 标注适用下界

#### Task 1.3: BIP/kij 参数库与混合物 VLE
- **目标**：实现混合物 bubble/dew point 计算，建立 BIP 参数数据库
- **依赖**：T1.1, T1.2
- **修改内容**：
  - 文件 `data/parameters/bip.json`：6×6 kij 矩阵 + 温度依赖参数 + 来源（文献/DWSIM 回归）+ 不确定度
  - 文件 `src/h2iso/vle/mixing.py`：
    - `kij_matrix(T) -> ndarray(6,6)`：BIP 参数矩阵
    - `bubble_pressure(T, x, eos) -> (P, y)`：泡点压力 + 气相组成
    - `dew_pressure(T, y, eos) -> (P, x)`：露点压力 + 液相组成
    - `bubble_temperature(P, x, eos) -> (T, y)`：泡点温度
    - `kvalue(T, P, x, eos) -> ndarray(6)`：K-value 向量
  - 文件 `src/h2iso/vle/flash.py`：
    - `flash_TP(T, P, z, eos) -> (V, x, y)`：TP flash
    - `rachford_rice(z, K) -> V`：Rachford-Rice 求解
- **修改边界**：不实现三相闪蒸（氢同位素体系不涉及），不实现固相
- **测试要求**：
  - `pytest tests/test_vle/test_mixing.py`
  - 验证：(1) 纯组分 bubble_P == pvap ± 浮点误差；(2) K-value 排序 K_H2 > K_HD > K_D2 > K_HT > K_DT > K_T2（挥发度递减）；(3) 质量守恒 z = V*y + (1-V)*x；(4) Wang 2022 CD2 进料组成在 90 kPa 下 flash 结果合理
- **验收标准**：
  - ✅ 纯组分 bubble/dew 与 T1.1 蒸汽压一致（相对偏差 < 1e-10）
  - ✅ 二元等温 Pxy 图趋势与 Souers/文献一致
  - ✅ Wang 2022 CD2 进料条件下 K-value 量级合理（0.5-2.0 区间）
  - ✅ flash 质量守恒残差 < 1e-12
  - ✅ CasADi SX 模式 flash 可微分
- **潜在风险**：部分 kij 值文献数据稀疏（尤其 HT-DT 对）→ 用组合规则估算 + 标注不确定度；Rachford-Rice 在近泡/露点区域数值敏感 → 添加 bounded Newton

#### Task 1.4: 催化同位素交换平衡
- **目标**：实现给定温度和原子比下的同位素交换平衡组成求解
- **依赖**：T0.1
- **修改内容**：
  - 文件 `data/parameters/equilibrium.json`：6 个交换反应的 K_eq(T) 多项式系数 + 来源
  - 文件 `src/h2iso/equilibrator/__init__.py`
  - 文件 `src/h2iso/equilibrator/equilibrium.py`：
    - `keq(T, reaction) -> float`：单个反应平衡常数
    - `equilibrium_composition(T, atom_fractions) -> ndarray(6)`：给定 {H, D, T} 原子比，求平衡分子组成
    - 内部使用 Newton 或 CasADi rootfinder 求解约束方程组
- **修改边界**：不实现反应动力学（LHHW），不实现催化器 holdup，不实现 PFR/CSTR 模型
- **测试要求**：
  - `pytest tests/test_equilibrator/test_equilibrium.py`
  - 验证：(1) 纯 H+D 原子在 25 K 给出 K_eq(HD) ≈ 3.8（文献值）；(2) 极端情况 — 纯同位素进料保持不变；(3) 原子守恒（H+D+T 守恒）；(4) 质量守恒
- **验收标准**：
  - ✅ K_eq(H₂+D₂⇌2HD) 在 25 K ≈ 3.8（相对偏差 < 5%）
  - ✅ 原子守恒残差 < 1e-12
  - ✅ 迭代收敛（< 20 次 Newton 步）
  - ✅ CasADi 兼容
- **潜在风险**：6 组分 3 独立平衡 + 原子守恒 → 自由度分析需仔细；可能需要指定初始猜测策略

#### Task 1.5: VLE 集成测试与 DWSIM/文献对标
- **目标**：将 VLE 模块作为整体进行集成验证，与 DWSIM 和 Wang 2022 数据对标
- **依赖**：T1.1, T1.2, T1.3, T1.4
- **修改内容**：
  - 文件 `tests/test_vle/test_integration.py`：集成测试
  - 文件 `tests/test_vle/test_wang2022_vle.py`：与 Wang 2022 进料条件的 VLE 对标
  - 文件 `docs/validation/vle_report.md`：VLE 验证报告模板
- **修改边界**：不修改 VLE 实现代码（只加测试），不修改 fixtures
- **测试要求**：
  - `pytest tests/test_vle/ -v --tb=short`
  - 全部通过
- **验收标准**：
  - ✅ Wang 2022 CD2 进料条件下 K-value 与 Aspen 文献值偏差 < 10%
  - ✅ DWSIM SRK 模式下 K-value 趋势一致（同挥发度顺序）
  - ✅ 全 VLE 测试 0 failures
  - ✅ 验证报告列出每个组分对每个来源的偏差
- **潜在风险**：DWSIM 使用经典 SRK 无量子修正，偏差可能达 5-15% → 预期偏差，不视为 failure

---

### Phase 2: L2-CasADi 稳态 MESH 求解器

#### Task 2.1: 单板 MESH 方程构建
- **目标**：用 CasADi 符号框架构建单个理论板的 MESH (Material, Equilibrium, Summation, Heat) 方程组
- **依赖**：T1.3（需要 VLE K-value 函数）
- **修改内容**：
  - 文件 `src/h2iso/mesh/__init__.py`
  - 文件 `src/h2iso/mesh/stage.py`：
    - `class Stage`：单板方程构建器
      - `material_balance(L_in, V_in, L_out, V_out, x_in, y_in, x_out, y_out, F, z) -> residual`
      - `equilibrium(T, P, x, y, K) -> residual`（y_i - K_i * x_i = 0）
      - `summation(x, y) -> residual`（Σx=1, Σy=1）
      - `energy_balance(T, H_L, H_V, Q) -> residual`
    - 所有函数返回 CasADi SX 表达式
  - 文件 `src/h2iso/mesh/enthalpy.py`：
    - `liquid_enthalpy(T, x) -> SX`
    - `vapor_enthalpy(T, y) -> SX`
    - 基于 Souers 热容数据
- **修改边界**：不实现多板组装（T2.2 做），不实现求解逻辑
- **测试要求**：
  - `pytest tests/test_mesh/test_stage.py`
  - 验证：(1) 单板在已知解处 residual → 0；(2) 符号 Jacobian 可计算（`casadi.jacobian`）；(3) 6 组分单板方程数 = 2*6+2+1 = 15（6 物料 + 6 相平衡 + 2 归一化 + 1 能量）
- **验收标准**：
  - ✅ 单板方程在已知稳态解处残差 < 1e-10
  - ✅ Jacobian 非奇异（条件数 < 1e8）
  - ✅ CasADi 符号图构建时间 < 1s
- **潜在风险**：能量方程的焓函数在低温下可能数值刚性 → 考虑 constant molar overflow (CMO) 简化模式作为 fallback

#### Task 2.2: N 板塔组装与 NLP 构建
- **目标**：将 N 个单板方程组装为完整精馏塔 NLP 问题
- **依赖**：T2.1
- **修改内容**：
  - 文件 `src/h2iso/mesh/column.py`：
    - `class Column`：
      - `__init__(n_stages, feed_stage, feed, pressure_profile, specs)`
      - `build_nlp() -> (nlp_dict, x0, lbx, ubx, lbg, ubg)`：构建 CasADi NLP
      - `solve(options=None) -> ColumnResult`：调用 IPOPT 求解
      - `specs`：支持 {reflux_ratio + D/F} 或 {reflux_ratio + bottoms_rate} 等规格组合
    - `class ColumnResult`：
      - `T_profile`, `x_profile`, `y_profile`, `L_profile`, `V_profile`
      - `condenser_duty`, `reboiler_duty`
      - `convergence_info`（iterations, residual, IPOPT status）
  - 文件 `src/h2iso/mesh/scaling.py`：
    - 变量 scaling 策略（T/100, x*1, P/1e5, flow/F_total）
    - bounds 设置（x ∈ [0,1], T ∈ [14,35], P ∈ [5e4, 2e5]）
- **修改边界**：不实现 continuation（T2.3 做），不实现多塔
- **测试要求**：
  - `pytest tests/test_mesh/test_column.py`
  - 验证：(1) N=15 板 Wang 2022 CD2 配置收敛；(2) 质量守恒残差 < 0.01%；(3) 温度 profile 单调递增（顶→底）
- **验收标准**：
  - ✅ N=15 板收敛，IPOPT status = "Solve_Succeeded"
  - ✅ 塔顶 D₂ 纯度 > 99%（15 板不要求达到 75 板的 99.97%）
  - ✅ 物料守恒总误差 < 0.01%
  - ✅ 求解时间 < 10s（15 板）
- **潜在风险**：IPOPT 对初值敏感 → T2.3 的 continuation 是解决方案；先用 linear T profile + equal molar split 作为 naive 初值

#### Task 2.3: Continuation 与高板数求解
- **目标**：实现从短塔到长塔的分步 continuation 策略，稳定求解 75-100 板
- **依赖**：T2.2
- **修改内容**：
  - 文件 `src/h2iso/mesh/continuation.py`：
    - `class ContinuationSolver`：
      - `add_step(param, target, n_substeps)`：添加参数变化步骤
      - `solve(column_base) -> ColumnResult`：逐步执行 continuation
    - 支持的 continuation 参数：N（板数）、R（回流比）、D/F、feed 组成
    - warm start：上一步的解作为下一步初值
    - 自适应步长：失败时自动减半步长，成功时恢复
  - 文件 `src/h2iso/mesh/homotopy.py`：
    - `homotopy_solve(column, simplified, actual, lambda_steps) -> ColumnResult`
    - simplified: CMO 假设（无能量方程）→ actual: 完整 MESH
- **修改边界**：不修改 `column.py` 的 API（只在内部调用 continuation），不实现多塔串联
- **测试要求**：
  - `pytest tests/test_mesh/test_continuation.py`
  - 验证：(1) N=15→30→60→75 分步 continuation 成功；(2) N=75 板 Wang 2022 CD2 收敛；(3) 步长回退机制在人为 bad 初值下能自动恢复
- **验收标准**：
  - ✅ Wang 2022 CD2 75 板收敛，D₂ 塔顶纯度 ≥ 99.97%（与 Aspen 文献偏差 < 0.1%）
  - ✅ 温度 profile 与 Wang 2022 Table 8 偏差 < 0.5 K
  - ✅ 热负荷偏差 < 10%
  - ✅ 100 板大塔可收敛（可能需要更多 continuation 步）
  - ✅ 求解时间 < 60s（75 板，含 continuation）
- **潜在风险**：75 板高纯度区域 x_i 接近 0/1 导致 log 奇异 → 添加 epsilon barrier 或变量替换（logit）

#### Task 2.4: Profile 输出与 Modelica 接口
- **目标**：将 CasADi 求解结果导出为 tricys/Modelica 可消费的初始化文件格式
- **依赖**：T2.2
- **修改内容**：
  - 文件 `src/h2iso/mesh/export.py`：
    - `export_csv(result, path)`：逐板 T, x_i, y_i, L, V 表格
    - `export_json(result, path)`：结构化 JSON（含 metadata）
    - `export_mat(result, path)`：MAT 文件（OpenModelica `readMatrix` 兼容）
  - 文件 `src/h2iso/codegen/__init__.py`
  - 文件 `src/h2iso/codegen/modelica_init.py`：
    - `generate_init_script(result, model_name) -> str`：生成 `.mos` 初始化脚本
- **修改边界**：不生成完整 Modelica 模型（只生成初值/参数赋值），不修改 tricys 侧代码
- **测试要求**：
  - `pytest tests/test_mesh/test_export.py`
  - 验证：(1) CSV 可被 pandas 读取且列名正确；(2) JSON schema 验证通过；(3) MAT 文件可被 `scipy.io.loadmat` 读取
- **验收标准**：
  - ✅ 三种格式均可正确导出和重新读入
  - ✅ 读入后数值与原始 result 一致（< 1e-15 偏差）
  - ✅ MAT 格式与 OpenModelica `readMatrix` 兼容
- **潜在风险**：MAT v4 vs v5 格式兼容性 → 使用 scipy.io.savemat(..., do_compression=False, format='4')

#### Task 2.5: Wang 2022 全面验证与 Go/No-Go
- **目标**：用 Wang 2022 ISS-I CD2（75板）和 ISS-O 三塔配置进行完整验证，判定 Go/No-Go
- **依赖**：T2.3, T1.5
- **修改内容**：
  - 文件 `tests/test_mesh/test_wang2022_mesh.py`：
    - `test_cd2_75stages()`：ISS-I CD2 全验证
    - `test_isso_cd1/cd2/cd3()`：ISS-O 三塔逐个验证
  - 文件 `docs/validation/mesh_report.md`：MESH 求解器验证报告
  - 文件 `benchmark/wang2022_casadi_results.json`：CasADi 结果存档
- **修改边界**：不修改求解器代码（只加测试和报告）
- **测试要求**：
  - `pytest tests/test_mesh/test_wang2022_mesh.py -v`
- **验收标准**：
  - ✅ CD2 75 板：D₂ 顶纯度偏差 < 0.1%，温度偏差 < 0.5 K，热负荷偏差 < 10%
  - ✅ ISS-O 至少 2/3 塔收敛（CD1 板数最多，可能最难）
  - ✅ Go/No-Go 判定文档化：若全部通过则 Go（继续 Modelica L3）；若 CD2 失败则需要回溯改进 continuation
- **潜在风险**：ISS-O 某些塔板数超 100 + 回流比极高 → 可能需要更激进的 continuation；允许部分 xfail 但必须有分析

---

### Phase 3: 文档、CLI 与发布准备

#### Task 3.1: API 文档与使用示例
- **目标**：建立完整的 API 文档和使用教程
- **依赖**：T1.5, T2.5
- **修改内容**：
  - 文件 `docs/index.md`：项目首页
  - 文件 `docs/quickstart.md`：5 分钟上手
  - 文件 `docs/api/vle.md`：VLE API 参考
  - 文件 `docs/api/mesh.md`：MESH API 参考
  - 文件 `docs/examples/single_column.py`：单塔求解示例
  - 文件 `mkdocs.yml`：文档配置
- **修改边界**：不修改源代码
- **测试要求**：
  - `mkdocs build` 无错误
- **验收标准**：
  - ✅ 文档覆盖所有 public API
  - ✅ quickstart 示例可独立运行
  - ✅ 验证报告链接完整
- **潜在风险**：无

#### Task 3.2: CLI 接口
- **目标**：提供命令行工具用于快速计算
- **依赖**：T2.2
- **修改内容**：
  - 文件 `src/h2iso/cli.py`：
    - `h2iso flash --T 22 --P 90000 --z "H2:0.1,D2:0.5,T2:0.4"`
    - `h2iso column --config column.json --output results/`
    - `h2iso export --input results.json --format mat`
  - `pyproject.toml` 中 `[project.scripts]` 注册入口
- **修改边界**：CLI 仅调用已有 API，不增加新计算逻辑
- **测试要求**：
  - `h2iso flash --help` 输出帮助信息
  - `h2iso column --config tests/fixtures/wang2022/wang2022_issi_cd2.json` 收敛
- **验收标准**：
  - ✅ 三个子命令均可运行
  - ✅ 输出格式整洁（表格或 JSON）
- **潜在风险**：无

## Execution Wave（并行执行波次）

| Wave | 可并行 Task | 依赖已完成 |
|------|------------|------------|
| W1 | T0.1, T0.2 | — |
| W2 | T1.1, T1.4 | W1 |
| W3 | T1.2 | T1.1 |
| W4 | T1.3 | T1.1, T1.2 |
| W5 | T1.5, T2.1 | T1.3, T1.4 |
| W6 | T2.2 | T2.1 |
| W7 | T2.3, T2.4 | T2.2 |
| W8 | T2.5 | T2.3, T1.5 |
| W9 | T3.1, T3.2 | T2.5 |

## 回归检查清单

- [ ] `pip install -e ".[dev,solver]"` 无错误
- [ ] `pytest tests/ -x --tb=short` 全部通过
- [ ] `ruff check src/ tests/` 无错误
- [ ] Wang 2022 CD2 75 板 CasADi 收敛 (Go/No-Go 核心指标)
- [ ] 所有物性参数标注来源和不确定度
- [ ] CasADi optional dependency 不影响基础 VLE 功能（仅 numpy 也能用）
- [ ] 导出的 MAT 文件可被 OpenModelica 读取

## 审查日志

| 轮次 | 聚焦 | 发现问题数 | 已修正 | 剩余 |
|------|------|-----------|--------|------|
| R1 | 结构完整性 | 3 | 3 | 0 |
| R1.5 | 外部引用事实核查 | 2 | 2 | 0 |
| R2 | 可执行性 | 2 | 2 | 0 |
| R3 | 风险与边缘 | 1 | 1 | 0 |
| **终止** | **T1 — 收敛终止** | | | **0** |

### Completion Summary

| 维度 | 结果 |
|------|------|
| 背景与目标 | 完整 |
| 技术方案 | 完整 |
| Error & Rescue Map | 6 条路径已覆盖，0 CRITICAL GAP |
| 执行计划 | 3 Phase, 12 Task |
| 回归检查清单 | 7 项目特定检查 |
| 已知局限 | 无 |

### R1 Issues
- **Issue R1-1**: 缺少 Error & Rescue Map → 已添加 ✅
- **Issue R1-2**: 非目标缺少 ortho/para 说明 → 已补充 ✅
- **Issue R1-3**: 已有代码复用分析缺失 → 已添加 ✅

### R1.5 Issues
- **Issue R1.5-1**: CasADi API 引用 (`casadi.jacobian`) 需确认 → [verified: CasADi docs, `casadi.jacobian(expr, x)` 是正确 API] ✅
- **Issue R1.5-2**: `scipy.io.savemat` format='4' 参数存在性 → [verified: scipy docs, `format` param 接受 '4' 或 '5'] ✅

### R2 Issues
- **Issue R2-1**: T2.2 验收标准"15 板 D₂ > 99%"可能过松 — 15 板在 R=15 下确实约 99%+ → 保持，合理 ✅
- **Issue R2-2**: T1.3 依赖应包含 T1.2（量子修正影响 K-value）→ 已修正依赖关系 ✅

### R3 Issues
- **Issue R3-1**: T2.3 中 logit 变量替换与 CasADi bounds 可能冲突 → 在潜在风险中标注"epsilon barrier 优先于 logit，因 logit 改变 NLP landscape" ✅
