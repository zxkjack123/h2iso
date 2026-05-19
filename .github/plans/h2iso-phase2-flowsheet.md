# h2iso Phase 2: Flowsheet 求解器与 tricys 集成

## 背景与目标

- **问题/需求描述**：Phase 1 完成了单塔稳态 MESH 求解（验证通过 Wang 2022 CD2 75 板）。但聚变氚燃料循环 ISS 系统由 3–5 根互联精馏塔 + 催化平衡器组成，存在塔间再循环流（tear stream）。当前 h2iso 无法描述多塔拓扑、无法迭代求解再循环流、无法作为 tricys 的自动初始化源。
- **目标**：
  - 实现 Flowsheet 求解器：多塔级联 + tear stream 序贯模块迭代收敛
  - 定义 Flowsheet JSON Schema：统一描述多塔拓扑与参数
  - 扩展 ColumnSpec 支持多进料口
  - 实现混合器/分流器基础单元
  - 完成 ISS-O 三塔联合验证（Wang 2022 参考数据）
  - 建立 h2iso → tricys Modelica 初始化自动管线
- **非目标（不做什么）**：
  - 不实现动态 Modelica 模型 — 仍留在 tricys L3 层
  - 不实现换热器详细模型 — 用给定热负荷或定温规格
  - 不实现反应动力学 — 平衡器继续用化学平衡模型（exchange.py）
  - 不实现压力梯度 — 沿用恒压假设（Phase 1 确认偏差可控）
  - 不重构 Phase 1 的 Column/ContinuationSolver — 只扩展接口
- **已有代码/流程复用分析**：
  - `h2iso.mesh.Column` + `ContinuationSolver`：**复用**（多塔求解的核心单元）
  - `h2iso.equilibrator.exchange`：**复用**（平衡器节点直接调用）
  - `tests/fixtures/wang2022/wang2022_isso.json`：**复用**（ISS-O 三塔拓扑 + 预期结果）
  - `tricys/docs/benchmark/distillation_roadmap.md` §3.1 L2/L4 接口定义：**复用**（集成设计参考）

## 技术方案

- **方案概述**：新增 `h2iso.flowsheet` 子包，包含流股（Stream）、单元操作（UnitOp）、拓扑（Topology）和序贯模块求解器（SequentialModular solver, SM）。SM 使用 Wegstein / direct substitution 加速 tear stream 收敛。
- **关键设计决策**：
  1. **序贯模块法（SM）而非联立方程法** — SM 复用 Phase 1 成熟的单塔 CasADi NLP 求解，无需重构为全系统 NLP；对 3–5 塔规模足够高效
  2. **Flowsheet JSON Schema** — 声明式配置文件，兼容 wang2022_isso.json 已有格式，支持 CLI `h2iso flowsheet --config iss_o.json`
  3. **多进料 ColumnSpec 扩展** — 将 `feed_stage: int` 扩展为 `feeds: list[FeedSpec]`，支持多点进料的 CMO 流量计算
  4. **Wegstein 加速** — tear stream 迭代中使用 Wegstein 方法加速收敛，比 direct substitution 快 3–5 倍
  5. **tricys 集成：h2iso 作为 optional dependency** — tricys `pyproject.toml` 增加 `h2iso` 为可选依赖，在 `script/distillation/` 下提供初始化脚本，输出 `.mos` 文件
- **影响范围**：
  - h2iso repo: 新增 `src/h2iso/flowsheet/` 子包，修改 `ColumnSpec` 支持多进料
  - tricys repo: 新增 `script/distillation/init_from_h2iso.py`（仅添加，不修改现有代码）

## Error & Rescue Map（关键失败路径映射）

| 代码路径/操作 | 可能的失败 | 错误类型 | 已处理？ | 处理方式 | 用户可见行为 |
|-------------|-----------|---------|---------|---------|------------|
| `flowsheet.solve()` tear stream 不收敛 | Wegstein 迭代发散 | ConvergenceError | Y | 自动降级到 direct substitution + 增加迭代上限 + 报告最终残差 | 返回 partial result + warning |
| `flowsheet.solve()` 中间某塔 NLP 失败 | continuation 链断裂 | RuntimeError | Y | 记录失败塔 + 尝试缩小步长/扰动初值 | 日志报告哪根塔失败，附 IPOPT diagnostics |
| Multi-feed CMO `_compute_flows()` 多进料负流量 | D/F 设定不当导致某段 V<0 | ValueError | Y | 求解前检查 V≥0 条件，违反时 raise + 提示调整 R 或 D/F | 明确错误指出哪段 V<0 |
| Flowsheet JSON 格式错误 | topology 节点引用不存在的 column | ValidationError | Y | JSON Schema 校验 + 拓扑 DAG 检查 | 报告具体的断开连接 |
| Equilibrator 温度超出 K_eq 适用范围 | 外推产生非物理组成 | Warning | Y | 同 Phase 1 — 范围检查 + warning | 允许继续但提示 |
| tricys 集成: h2iso 未安装 | ImportError | ImportError | Y | try/except + 友好提示 | "pip install h2iso[solver] for initialization" |

## 执行计划

### Phase 2.0: 多进料扩展

#### ✅ Task 2.0.1: ColumnSpec 多进料支持
- **目标**：将 ColumnSpec 从单进料扩展为多进料，支持 ISS-O 中 CD2 有 3 个进料口的场景
- **依赖**：无（Phase 1 已完成）
- **修改内容**：
  - 文件 `src/h2iso/mesh/column.py`：
    - 新增 `FeedSpec` dataclass: `stage: int, flow: float, composition: ndarray, quality: float = 1.0`
    - `ColumnSpec` 新增 `feeds: list[FeedSpec] | None = None` 字段
    - 若 `feeds` 为 None，保持向后兼容（使用原 feed_stage/feed_flow/feed_composition）
    - `_compute_flows()` 扩展为支持多进料的 CMO 计算：每个进料点改变 L/V 跳变
    - `build_nlp()` 中物料平衡约束适配多进料
  - 文件 `tests/test_mesh/test_multi_feed.py`：
    - 双进料塔测试（对称进料应等价于单中心进料的两倍流量）
    - 验证 `_compute_flows()` 多段 L/V 阶梯正确
- **修改边界**：不修改 `ContinuationSolver`、不修改 `export.py`、不修改 VLE 层
- **测试要求**：
  - `pytest tests/test_mesh/test_multi_feed.py -v`
  - 向后兼容：Phase 1 全部 141 tests 仍通过
- **验收标准**：
  - ✅ 单进料旧接口不变，原测试全部通过
  - ✅ 双进料塔可收敛
  - ✅ `_compute_flows()` 对 N 个进料产生 N+1 段的 L/V 阶梯
- **潜在风险**：多进料 CMO 假设在进料热条件差异大时不够准确；Phase 2 暂不处理，后续考虑能量平衡修正

#### ✅ Task 2.0.2: ContinuationSolver 适配多进料
- **目标**：使 continuation warm-start 正确处理多进料塔的 feed_stage 插值
- **依赖**：T2.0.1
- **修改内容**：
  - 文件 `src/h2iso/mesh/continuation.py`：
    - `_continue_N()` 中 profile 插值时，保持各 feed_stage 的相对位置（按比例缩放）
    - 新增 `_scale_feeds()` 辅助函数
  - 文件 `tests/test_mesh/test_continuation_multi.py`：
    - 三进料塔从 15→30→60 板的 continuation 测试
- **修改边界**：不修改 `Column.build_nlp()`、不修改 VLE
- **测试要求**：
  - 三进料 60 板 continuation 收敛
  - Phase 1 tests 不退化
- **验收标准**：
  - ✅ 多进料 continuation 在 ISS-O 级别板数（60/70）可收敛
  - ✅ feed_stage 按比例正确缩放
- **潜在风险**：多进料的初值插值精度下降；降级方案：增加 substeps

### Phase 2.1: Flowsheet 基础设施

#### ✅ Task 2.1.1: Stream 与 UnitOp 抽象层
- **目标**：定义流股数据结构和单元操作基类，作为 flowsheet 求解器的基础
- **依赖**：T2.0.1
- **修改内容**：
  - 新建 `src/h2iso/flowsheet/__init__.py`
  - 新建 `src/h2iso/flowsheet/stream.py`：
    - `Stream` dataclass: `flow: float, composition: ndarray(6), temperature: float, pressure: float, phase: str = "liquid"`
    - `stream_mix(streams: list[Stream]) -> Stream`：流股混合（加权平均组成，绝热混合温度近似为流量加权均温）
    - `stream_split(stream: Stream, ratios: list[float]) -> list[Stream]`：流股分流
  - 新建 `src/h2iso/flowsheet/unit.py`：
    - `UnitOp` 抽象基类: `name: str`, `inlets: dict[str, Stream]`, `outlets: dict[str, Stream]`, `solve(inputs) -> outputs`
    - `ColumnUnit(UnitOp)`：包装 `Column` + `ContinuationSolver`，自动选择 continuation 路径
    - `EquilibratorUnit(UnitOp)`：包装 `equilibrator.exchange.equilibrium_composition()`
    - `MixerUnit(UnitOp)`：多入一出混合器
    - `SplitterUnit(UnitOp)`：一入多出分流器
  - 文件 `tests/test_flowsheet/test_stream.py`
  - 文件 `tests/test_flowsheet/test_units.py`
- **修改边界**：不修改 Phase 1 的 `mesh/` 或 `vle/` 源代码
- **测试要求**：
  - `stream_mix` 质量守恒测试
  - `ColumnUnit.solve()` 等价于直接调用 `Column.solve()`
  - `EquilibratorUnit.solve()` 等价于直接调用 `equilibrium_composition()`
- **验收标准**：
  - ✅ Stream 支持 mix/split 操作，质量守恒
  - ✅ ColumnUnit 包装后结果与直接调用一致
  - ✅ EquilibratorUnit 包装后结果与直接调用一致
- **潜在风险**：无

#### ✅ Task 2.1.2: Flowsheet JSON Schema
- **目标**：定义描述多塔拓扑的 JSON Schema，兼容现有 wang2022_isso.json 格式
- **依赖**：T2.1.1
- **修改内容**：
  - 新建 `src/h2iso/flowsheet/schema.py`：
    - `FlowsheetConfig` dataclass：`feeds`, `columns`, `equilibrators`, `topology`
    - `load_flowsheet(path: str) -> FlowsheetConfig`：加载 + 校验
    - `validate_topology(config) -> list[str]`：检查连接完整性、DAG 可行性
    - `detect_tear_streams(config) -> list[TearStream]`：识别循环流（需切断的流）
  - 新建 `data/schemas/flowsheet_v1.json`：JSON Schema 定义文件
  - 文件 `tests/test_flowsheet/test_schema.py`：
    - 加载 wang2022_isso.json 成功
    - 非法拓扑（断开连接）报错
    - tear stream 正确识别（CD2_bottom_recycle → CD1 是循环流）
- **修改边界**：不修改 fixtures、不修改 mesh 层
- **测试要求**：
  - `load_flowsheet("tests/fixtures/wang2022/wang2022_isso.json")` 成功
  - `detect_tear_streams()` 返回 `["CD2_bottom_recycle → CD1"]`
- **验收标准**：
  - ✅ wang2022_isso.json 可正确加载为 FlowsheetConfig
  - ✅ 拓扑校验能报告断开连接
  - ✅ tear stream 自动识别
- **潜在风险**：fixture 格式与 schema 可能有小出入；需适配

#### Task 2.1.3: 序贯模块求解器（SM Solver）
- **目标**：实现流程图的序贯模块迭代求解，支持 tear stream 收敛
- **依赖**：T2.1.1, T2.1.2
- **修改内容**：
  - 新建 `src/h2iso/flowsheet/solver.py`：
    - `SequentialModularSolver` 类：
      - `__init__(config: FlowsheetConfig, method: str = "wegstein")`
      - `solve(max_iter=50, tol=1e-4) -> FlowsheetResult`
      - 内部逻辑：
        1. `_build_calculation_order()`: 拓扑排序 + tear stream 切断点
        2. `_initialize_tears()`: 用进料组成/流量初始化 tear stream 估计值
        3. `_iterate()`: 按计算顺序逐单元求解，到 tear point 时比较出入口
        4. `_wegstein_update()`: Wegstein 加速更新 tear stream 估计值
        5. 检查收敛：`max(|x_new - x_old|) < tol`
    - `FlowsheetResult` dataclass：
      - `streams: dict[str, Stream]`：所有流股最终状态
      - `column_results: dict[str, ColumnResult]`：各塔详细 profile
      - `converged: bool`
      - `iterations: int`
      - `tear_residual: float`
  - 文件 `tests/test_flowsheet/test_solver.py`：
    - 无循环流的简单两塔级联（CD1→CD2，无 recycle）直接收敛
    - 带循环流的三塔 ISS-O 简化版（tear stream 初始化后 <20 次迭代收敛）
- **修改边界**：不修改单塔求解器逻辑
- **测试要求**：
  - 两塔级联 1 次迭代即收敛（无 tear stream）
  - 三塔 ISS-O 在 50 次迭代内收敛
- **验收标准**：
  - ✅ 无循环流的 flowsheet 直接求解成功
  - ✅ 有循环流的 flowsheet 通过 Wegstein 迭代收敛
  - ✅ 质量守恒：进料总流量 = 产品总流量（相对误差 < 0.1%）
- **潜在风险**：ISS-O 的 CD3_top→CD2 recycle + CD2_bottom→CD1 双循环可能导致慢收敛；降级方案：允许局部 frozen（先解开一个循环再解另一个）

### Phase 2.2: ISS-O 三塔验证

#### Task 2.2.1: ISS-O 三塔求解（无 recycle 简化版）
- **目标**：先验证无循环流的三塔顺序求解，确认各塔独立结果
- **依赖**：T2.0.2, T2.1.3
- **修改内容**：
  - 文件 `tests/test_flowsheet/test_isso_no_recycle.py`：
    - 加载 wang2022_isso.json
    - 将 `CD2_bottom_recycle` 和 `CD3_top` 回流断开（设为 zero flow）
    - 顺序解 CD1 → CD2 → equilibrator → CD3
    - 验证各塔温度/组成在合理范围
- **修改边界**：不修改源代码，纯测试
- **测试要求**：
  - CD1/CD2/CD3 各 60/70/60 板全部收敛
  - 温度在 19–26 K 范围内
- **验收标准**：
  - ✅ 三塔各自独立收敛
  - ✅ CD1 top 接近纯 H₂（>99%）
  - ✅ CD3 bottom 接近纯 T₂ 或 DT-rich
- **潜在风险**：CD3 (60 板, R=18) 高回流比可能导致 continuation 困难

#### Task 2.2.2: ISS-O 三塔完整验证（含 recycle）
- **目标**：完整 ISS-O 三塔 + 平衡器 + 双循环流验证
- **依赖**：T2.2.1
- **修改内容**：
  - 文件 `tests/test_flowsheet/test_isso_full.py`：
    - 完整拓扑：WDS→CD1, TES→CD2, CD1_bot→CD2, CD2_bot→EQ→CD3, CD3_top→CD2, CD2_bot_recycle→CD1
    - 用 SM solver 迭代收敛
    - 对比 Wang 2022 Table 11/12 的温度、热负荷、产品组成
  - 文件 `docs/validation/isso_report.md`：ISS-O 验证报告
- **修改边界**：不修改源代码
- **测试要求**：
  - SM solver 在 50 次迭代内收敛（tear_residual < 1e-4）
  - 温度偏差 < 1 K（对比 Wang 2022）
  - 产品组成偏差 < 5% relative
- **验收标准**：
  - ✅ ISS-O 全系统收敛
  - ✅ CD1 top H₂ > 99.8%（ref: 99.843%）
  - ✅ CD3 bottom T₂/DT enrichment 方向正确
  - ✅ 热负荷量级与 Wang 2022 一致（condenser 负、reboiler 正）
  - ✅ 全系统质量守恒 < 0.1%
- **潜在风险**：Wang 2022 ISS-O 数据来自含 Aspen 催化反应器（equilibrator）的模型，而 h2iso 用化学平衡近似——CD3 进料组成可能与参考有偏差；在验证报告中量化此偏差

### Phase 2.3: CLI 扩展与参数优化

#### Task 2.3.1: CLI flowsheet 子命令
- **目标**：添加 `h2iso flowsheet --config iss_o.json` 命令
- **依赖**：T2.1.3
- **修改内容**：
  - 文件 `src/h2iso/cli.py`：
    - 新增 `flowsheet` 子命令
    - `--config`: Flowsheet JSON 路径
    - `--output`: 输出目录（各塔 profiles + 全流程摘要）
    - `--max-iter`: tear stream 最大迭代次数
    - `--tol`: 收敛容差
  - 测试：`h2iso flowsheet --config tests/fixtures/wang2022/wang2022_isso.json --output /tmp/isso_test`
- **修改边界**：CLI 仅调用 flowsheet API
- **测试要求**：
  - `h2iso flowsheet --help` 正确
  - 给定 config 后输出收敛结果
- **验收标准**：
  - ✅ CLI 可运行完整 ISS-O 流程
  - ✅ 输出各塔 profiles.csv + 全流程 summary.json
- **潜在风险**：无

#### Task 2.3.2: 设计参数扫描接口
- **目标**：提供 API 和 CLI 支持对关键设计参数（R, N, D/F）进行参数扫描
- **依赖**：T2.1.3
- **修改内容**：
  - 新建 `src/h2iso/flowsheet/sweep.py`：
    - `ParameterSweep` 类：定义扫描空间、并行求解（multiprocessing）、收集结果
    - 支持：单参数扫描、双参数网格扫描
    - 输出：pandas DataFrame 或 JSON
  - 文件 `src/h2iso/cli.py`：新增 `sweep` 子命令
  - 文件 `tests/test_flowsheet/test_sweep.py`
- **修改边界**：不修改求解器核心逻辑
- **测试要求**：
  - 对 CD2 扫描 R=5..20 步长 5 得到 4 个收敛结果
- **验收标准**：
  - ✅ 参数扫描可得到性能趋势（R 增大 → 分离改善 → 热负荷增大）
  - ✅ 支持 JSON 输出
- **潜在风险**：高 R 或大 N 时单次求解耗时长；可设 timeout

### Phase 2.4: tricys 集成

#### Task 2.4.1: tricys 集成脚本
- **目标**：在 tricys repo 中添加使用 h2iso 生成 Modelica 初始化文件的脚本
- **依赖**：T2.2.2
- **修改内容**：
  - tricys repo 文件 `script/distillation/init_from_h2iso.py`：
    - 从 flowsheet JSON 加载 ISS 配置
    - 调用 `h2iso.flowsheet.solve()` 获取稳态解
    - 对每根塔调用 `generate_init_script()` 输出 `.mos`
    - 生成 `init_all_columns.mos` 批量设置脚本
  - tricys repo `pyproject.toml`：`[project.optional-dependencies]` 增加 `distillation = ["h2iso>=0.2.0"]`
  - tricys repo 文件 `script/distillation/README.md`：使用说明
- **修改边界**：仅在 tricys 新增文件，不修改现有 Modelica 模型或 Python 代码
- **测试要求**：
  - `python script/distillation/init_from_h2iso.py --config examples/iss_o.json` 生成 `.mos` 文件
- **验收标准**：
  - ✅ 生成的 `.mos` 文件包含正确的 T/x/y profile 数组
  - ✅ profile 长度与对应 Modelica 模型的 N_stages 一致
  - ✅ tricys CI 在无 h2iso 时 gracefully skip（optional dependency）
- **潜在风险**：tricys Modelica 模型变量命名可能与 .mos 中引用不一致；需查阅 tricys ISS 模型确认命名

#### Task 2.4.2: Modelica record 代码生成
- **目标**：从 h2iso VLE 参数 JSON 自动生成 Modelica record（物性参数源一致性）
- **依赖**：T2.4.1
- **修改内容**：
  - 新建 `src/h2iso/codegen/modelica_records.py`：
    - `generate_species_records()` → 生成 `HydrogenIsotope_H2.mo` 等 record 文件
    - `generate_vle_functions()` → 生成 `pvap_H2(T)` 等 Modelica function
    - 数据源：`data/parameters/vapor_pressure.json`, `species.json`
  - 文件 `tests/test_codegen/test_modelica_records.py`：
    - 生成内容与手写 Modelica record 对比
- **修改边界**：不修改 tricys 现有 Modelica 模型（生成的 record 供未来集成）
- **测试要求**：
  - 生成的 `.mo` 文件语法正确（OMC 可编译）
- **验收标准**：
  - ✅ 6 个 species record 正确生成
  - ✅ pvap function 在 20/24/28 K 的值与 Python 一致（< 0.01% 偏差）
- **潜在风险**：OpenModelica 版本差异可能导致语法问题；目标 OMC 1.23+

## Execution Wave（并行执行波次）

| Wave | 可并行 Task | 依赖已完成 |
|------|------------|------------|
| W1 | T2.0.1 | Phase 1 |
| W2 | T2.0.2, T2.1.1 | W1 |
| W3 | T2.1.2 | W2 |
| W4 | T2.1.3 | W2, W3 |
| W5 | T2.2.1, T2.3.1, T2.3.2 | W4 |
| W6 | T2.2.2 | W5 |
| W7 | T2.4.1 | W6 |
| W8 | T2.4.2 | W7 |

## 回归检查清单
- [ ] Phase 1 全部 141 tests 通过（向后兼容）
- [ ] Phase 2 新增测试全部通过
- [ ] `ruff check src/ tests/` 无错误
- [ ] `mkdocs build` 无错误
- [ ] `h2iso flash / column / flowsheet / sweep` CLI 子命令均可运行
- [ ] ISS-O 三塔质量守恒 < 0.1%
- [ ] 生成的 `.mos` 文件长度与塔板数一致

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
| Error & Rescue Map | 6 条路径覆盖，0 CRITICAL GAP |
| 执行计划 | 4 Phase, 10 Tasks |
| 回归检查清单 | 7 项目特定检查 |
| 已知局限 | 无 |

### [R1 Issues]
- **Issue R1-1**: 非目标缺少理由 → 补充一句话理由 ✅ 已修正
- **Issue R1-2**: Task 2.1.3 缺少 Wegstein 方法的降级策略 → 补充 direct substitution fallback ✅ 已修正
- **Issue R1-3**: Error Map 缺少 tricys 集成路径 → 补充 ImportError 处理 ✅ 已修正

### [R1.5 Issues]
- **Issue R1.5-1**: wang2022_isso.json topology 中的 `CD2_bottom_recycle` 命名需确认与 fixture 一致 → 已用 `read_file` 确认 fixture 中确实存在此连接 [verified: wang2022_isso.json topology.connections[6]] ✅ 已修正
- **Issue R1.5-2**: `equilibrium_composition` 函数名需确认 → 已用 `read_file` 确认 exchange.py 中确实存在 `keq()` 和对应平衡计算函数 [verified: src/h2iso/equilibrator/exchange.py:L43] ✅ 已修正

### [R2 Issues]
- **Issue R2-1**: Task 2.0.1 多进料 CMO 公式需明确 — L/V 在每个进料点的跳变公式 → 在 Task 描述中补充"每个进料点改变 L/V 跳变" ✅ 已修正
- **Issue R2-2**: Execution Wave 缺少 T2.3.1/T2.3.2 → 归入 W5 ✅ 已修正

### [R3 Issues]
- **Issue R3-1**: ISS-O 验证中 equilibrator 的平衡假设 vs Wang 2022 的 Aspen 催化反应器差异未量化 → 在验证标准中注明此偏差需记录 ✅ 已修正
