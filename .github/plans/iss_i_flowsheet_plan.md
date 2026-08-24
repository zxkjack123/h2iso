# ISS-I Full Flowsheet Model + Equilibrator Integration Plan

## 背景与目标

**问题描述**：构建 ISS-I（Inner fuel cycle）完整三塔级联模型，使 h2iso 的 sequential-modular 求解器能求解含 2 个平衡反应器（E1、E2）的 ISS-I 全系统。

**数据来源**：张世坤交付的 Aspen Plus T2-Threetowers4.bkp（2026-05-28），含：
- CD1=90 板 RR=50 D:F=0.3 进料板 72+50
- CD2=100 板 RR=60 D:F=0.78 进料板 45
- CD3=60 板 RR=295 D:F=0.085 进料板 45
- E1、E2（RCSTR 型平衡反应器）
- B13/B14/B15 压缩机 + B2-B6 加热器
- 完整拓扑：FROMTEP→CD1→B15→CD2→E1→CD1 回流 + CD2 底→B14→E2→B5→CD3→CD2 回流

**目标**：让 `python -m h2iso flowsheet --config iss_i.json` 能跑通 ISS-I 全系统（含 recycle），产出三塔温度剖面和产品组成。

**非目标**：
- 不含压缩机/加热器精确建模（用直通替代，T/P 不变）
- 不含分流器（CD2 底同时去 E1 和 E2 — 用简化替代方案）
- 不与张世坤的 Aspen 结果做逐组分定量对比（等补数据后另做）

---

## 修改方案

### 核心发现

调研发现 `EquilibratorUnit`、`EquilibratorConfig`、`ColumnUnit` 均已完整实现，`SequentialModularSolver._build_units()` 也已实例化 equilibrator。**问题不在这层**——问题在于：

1. **多 equilibrator 输出命名冲突**：当前 `_resolve_stream()` 用 `"equilibrator" in key` 匹配任何含 "equilibrator" 的 key，但多个 equilibrator 需要按名字区分（`E1_out` vs `E2_out`）
2. **ColumnConfig.feed_positions 的 key 与 connection.from_unit 不匹配**：JSON 中 feed_positions 写的是 `"equilibrator_output"` 而 connection 写的是 `"equilibrator"`
3. **Splitter 缺失**：ISS-I 中 CD2 底同时供 E1（回流）和 E2（去 CD3），需要分流器
4. **Equilibrator 顺序**：在拓扑排序中 equilibrator 需要出现在上下游之间

### 修改路径分类

| 文件 | 变更类型 | 预计行数 |
|------|---------|---------|
| `flowsheet/schema.py` | Light | +5 |
| `flowsheet/solver.py` | Light | +8 |
| `tests/fixtures/iss_i.json` | New | +150 |
| `tests/test_flowsheet/test_iss_i.py` | New | +100 |

**不再修改** `unit.py`、`equilibrator/` —— 现有实现已足够。

### 关键设计决策

#### D1：多个 Equilibrator 输出命名

**选择**：按 `{equilibrator_name}_out` 命名输出流（与 ColumnUnit 的 `{name}_distillate`/`{name}_bottoms` 一致）。

**替代方案（被拒绝）**：统一用 `"equilibrator_out"`。不选——多个 equilibrator 冲突。

**风险**：低。现有 ISS-O 只有 1 个 equilibrator，改后兼容。

#### D2：CD2 底分流方案

**选择**：在 ISS-I JSON 中加一个 `splitter` 配置——手动指定输出流量比（`E1_ratio`/`E2_ratio`），不新建 SplitterConfig 类。

**替代方案（被拒绝）**：用 `MixerUnit`/`SplitterUnit` 做正式 splitter。不选——增加复杂度，ISS-I 的 split 比例固定，可用 JSON 配置简化。

**风险**：中。分流比需要从 .bkp 反算或迭代调参得到。接受手工设定，后续可用优化器拟合。

#### D3：Compressor/Heater 处理

**选择**：不建模——直通处理（flow/comp/T 不变），仅用于 topology 完整性。

**替代方案（被拒绝）**：用 `PressureChangerUnit`。不选——这些单元不影响 ISS-I 的组分分离特性（CD 塔 + equilibrator 是核心）。

**风险**：低。只影响最终物流的 T/P 值，不影响组分分布。

---

## 执行计划

### Phase 1: Equilibrator 集成完善

#### Task 1.1: 修复多 equilibrator 输出解析

- **目标**：`_resolve_stream()` 能正确解析 `E1_out`、`E2_out` 等命名 equilibrator 输出
- **依赖**：无
- **修改内容**：
  - `src/h2iso/flowsheet/solver.py` 的 `_resolve_stream()` 方法（L387-392）
  - 将通用的 `"equilibrator" in key` 改为精确匹配 `{source_name}_out` 或 `{source_name}`
  - 同时支持旧 ISS-O 的单 `equilibrator` → `equilibrator_out` 向后兼容
- **修改边界**：不改 `_collect_inputs`、不改 `_build_units`、不改 `_execute_sequence`
- **质量检查**：
  - 现有 ISS-O 测试（`test_isso_full.py`、`test_isso_no_recycle.py`）必须通过
  - 新均衡器的输出以 `{name}_out` 形式存入 `self.streams`
- **验收标准**：
  - ✅ `test_isso_full.py` 全通过（13 tests）
  - ✅ `test_isso_no_recycle.py` 全通过
- **潜在风险**：低。仅改 5 行。

#### Task 1.2: 修复 feed_positions 和 connection 的 key 匹配

- **目标**：`_collect_inputs()` 和 `_resolve_stream()` 中的 feed_name 匹配覆盖 `"equilibrator"` → `"equilibrator_output"` 的自动变换
- **依赖**：Task 1.1
- **修改内容**：
  - `src/h2iso/flowsheet/solver.py` 的 `_collect_inputs()`（L322-344）
  - `ColumnConfig.feed_positions` 中的 key（如 `"equilibrator_output"`）需要能映射到 connection 中的 `"equilibrator"` 或 stream bank 中的 `"equilibrator_out"`
  - 在 `_resolve_stream()` 中添加自动嗅探：如果 `source_name` 不在 stream bank，尝试 `source_name.replace("_output", "")` 或 `source_name + "_out"`
- **修改边界**：不改 `_build_units`、不改 schema 解析
- **质量检查**：ISS-O 中的 `CD3.feed_positions={"equilibrator_output": 30}` 能正确解析到 `equilibrator_out`
- **验收标准**：
  - ✅ `test_isso_no_recycle.py::test_solver_converges` 通过
  - ✅ 新测试能加载 `iss_i.json` 并定位所有 feed
- **潜在风险**：低。向后兼容逻辑不破坏现有。

#### Task 1.3: 多 Equilibrator 小规模测试

- **目标**：创建一个 `MiniConfig`（1塔 + 2 equilibrator，无 recycle）验证路由逻辑
- **依赖**：Task 1.1, 1.2
- **修改内容**：
  - 新建 `tests/test_flowsheet/test_equilibrator_multi.py`
  - 构造一个迷你 flowsheet：Feed → CD_test (10板) → CD_bottom → E1 → E2 → Product
  - 验证：`equilibrium_composition()` 被调用两次（E1、E2 各自输出不同 aH/aD/aT）
  - 验证：`E1_out` 和 `E2_out` 两个流都在 stream bank 中
- **修改边界**：不改生产代码
- **验收标准**：
  - ✅ E1_out.composition ≠ E2_out.composition（不同 inlet → 不同 equilibrated output）
  - ✅ 所有流在 solver 后存在

### Phase 2: ISS-I Flowsheet JSON + 测试

#### Task 2.1: 创建 ISS-I FlowsheetConfig JSON

- **目标**：`tests/fixtures/wang2022/iss_i.json` — 完整的 ISS-I 三塔级联配置
- **依赖**：Task 1.1, 1.2
- **修改内容**：
  - 新建 `tests/fixtures/wang2022/iss_i.json`
  - 结构参考 `wang2022_isso.json`，参数从 `.bkp` 提取
  - 关键字段：

```json
{
  "source": { "authors": "Z. Shikun", "model": "ISS-I, T2-Threetowers4.bkp" },
  "feeds": {
    "FROMTEP": {
      "total_flow_mol_h": 30.63,  // TC5 default
      "composition_mole_fraction": { "H2": 0.1049, "HD": 0.1575, "D2": 0.05912, "HT": 0.2805, "DT": 0.2106, "T2": 0.1875 },
      "target_column": "CD1", "feed_stage": 72,
      "temperature_K": 23.89, "pressure_Pa": 100000
    }
  },
  "columns": {
    "CD1": { "total_stages": 90, "reflux_ratio": 50, "distillate_to_feed_ratio": 0.30,
              "feed_positions": { "FROMTEP": 72, "E1_output": 50 },
              "pressure_top_Pa": 90000, "pressure_bottom_Pa": 100000 },
    "CD2": { "total_stages": 100, "reflux_ratio": 60, "distillate_to_feed_ratio": 0.78,
              "feed_positions": { "CD1_bottom": 45 },
              "pressure_top_Pa": 90000, "pressure_bottom_Pa": 100000 },
    "CD3": { "total_stages": 60, "reflux_ratio": 295, "distillate_to_feed_ratio": 0.085,
              "feed_positions": { "E2_output": 45 },
              "pressure_top_Pa": 80000, "pressure_bottom_Pa": 100000 }
  },
  "equilibrators": {
    "E1": { "temperature": 25.0 },
    "E2": { "temperature": 25.0 }
  },
  "topology": {
    "connections": [
      {"from": "FROMTEP_feed", "to": "CD1", "stage": 72},
      {"from": "CD1_bottom", "to": "CD2", "stage": 45},
      {"from": "CD2_bottom", "to": "E1"},
      {"from": "E1", "to": "CD1", "stage": 50},
      {"from": "CD2_bottom", "to": "E2"},
      {"from": "E2", "to": "CD3", "stage": 45},
      {"from": "CD3_top", "to": "CD2", "stage": 45}
    ],
    "products": {
      "CD1_top": "WDS-H (H2-rich waste)",
      "CD2_top": "WDS-D (D2-rich waste)",
      "CD3_bottom": "T2-product (high purity)"
    },
    "simplification_notes": "Compressors and heaters omitted. CD2_bottom split to E1/E2 uses fixed ratio."
  }
}
```

- **修改边界**：不修改任何 Python 源代码
- **质量检查**：`load_flowsheet("iss_i.json")` 成功解析，`validate_topology()` 无错误
- **验收标准**：
  - ✅ `load_flowsheet()` 不抛异常
  - ✅ `validate_topology()` 返回空列表
  - ✅ 自动检测到 2 个 tear streams
- **潜在风险**：中。CD2_bottom 同时去 E1 和 E2 需 splitter——先用手动分流比（E1/E2 比例），从张世坤日后补数据中确定

#### Task 2.2: 处理 CD2 底分流（Splitter JSON 配置）

- **目标**：支持 flowsheet JSON 中的 `splitter` section，通过简化分流器路由
- **依赖**：Task 2.1
- **修改内容**：
  - 在 `iss_i.json` 中加 `splitter` section
  - 在 `schema.py` 加 `SplitterConfig`（或直接复用 ratio）
  - 方案选择：**最小侵入**——在 `_resolve_stream()` 中加逻辑：如果 `source_name` 对应一个在 split 列表中的 unit，按比例创建临时流
- **修改边界**：不改 `unit.py`，用 solver 内联逻辑
- **质量检查**：CD2 底 → E1 和 E2 的流量比例正确
- **验收标准**：
  - ✅ `load_flowsheet()` 解析 splitter config
  - ✅ solver 中 `_collect_inputs("E1")` 能获取分流后的 CD2_bottom 流
  - ✅ 分流后的总流量 = CD2_bottom.flow（守恒）
- **潜在风险**：中。Splitter 逻辑为最小实现，后续扩展为正式 SplitterUnit 类

#### Task 2.3: ISS-I 集成测试

- **目标**：验证 ISS-I 全系统能跑通，产出物理合理的解
- **依赖**：Task 2.1, 2.2
- **修改内容**：
  - 新建 `tests/test_flowsheet/test_iss_i.py`
  - 测试 1: 加载并验证拓扑（feed_positions、connections、tear detection）
  - 测试 2: 三塔全系统循环求解（Wegstein, max_iter=50, tol=1e-4）
  - 测试 3: 温度在物理范围（14-35 K）
  - 测试 4: CD3 底高 T2 富集（定性）
  - 测试 5: WDS 排气低 T（定性）
- **修改边界**：不依赖张世坤补数据，不做定量对比
- **质量检查**：所有测试通过，无爆炸/NaN
- **验收标准**：
  - ✅ 全系统收敛（iterations ≤ 50）
  - ✅ CD3_bottom T2 mole fraction > 0.5
  - ✅ CD1_top + CD2_top H2/D2 主导
  - ✅ 所有 T 在 [19, 35] K 内
- **潜在风险**：高。90/100 板 + 2 equilibrator + 2 recycle loops —— 求解器可能不收敛。需要在 iss_i.json 中正确配置 tear streams。

---

## Execution Wave

| Wave | 可并行 Task | 依赖已完成 |
|------|------------|------------|
| W1 | T1.1 | — |
| W2 | T1.2 | W1 |
| W3 | T1.3 | W2 |
| W4 | T2.1, T2.2 | W3 |
| W5 | T2.3 | W4 |

---

## Post-Execution Verification

### Automated
| ID | Description | Command |
|----|-------------|---------|
| V1 | ruff check | `ruff check src/ tests/` |
| V2 | Full regression | `pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e -q` |
| V3 | ISS-I specific | `pytest tests/test_flowsheet/test_iss_i.py -v` |

### Manual
- [ ] ISS-I 全系统求解器输出人工审查：温度值、组成分布是否物理合理
- [ ] 与 .bkp 中 CD2 的人工参数对比方向正确

---

## 审查日志

### R1 — 结构完整性
- 检查：Phase 覆盖目标、Task 依赖合理、修改边界清晰 ✓
- 发现：Phase 1 修复 equilibrator 集成（2 tasks），Phase 2 创建 JSON + 测试（3 tasks）
- 修正：无

### R1.5 — 外部引用事实核查
- `flowsheet/solver.py:L387-392` ✓（`_resolve_stream` 中 equilibrator 输出解析行）
- `flowsheet/unit.py:L192-226` ✓（`EquilibratorUnit` 实现）
- `flowsheet/schema.py:L38-43` ✓（`EquilibratorConfig` 定义）
- `flowsheet/schema.py:L79` ✓（`FlowsheetConfig.equilibrators` 字段）
- `flowsheet/schema.py:L246-300` ✓（`detect_tear_streams` 使用基于 DFS 的循环检测）
- `equilibrator/exchange.py:L94-196` ✓（`equilibrium_composition` — 在 25 K 下工作）
- `tests/fixtures/wang2022/wang2022_isso.json` ✓（现有 ISS-O fixture 格式）
- ✅ issue 清零

### R2 — 可执行性
- 检查：每个 Task 是否有明确的文件路径、修改行号、验收标准
- 发现：Task 2.2（Splitter）为最模糊项 —— 加上了具体实现方向（内联在 `_resolve_stream()` 中）
- ✅ issue 清零

### R2.8 — LLM 可执行性审查
逐字段检查：
- Task 1.1：`_resolve_stream()` L387-392 → 精确行号 ✓
- Task 1.2：`_collect_inputs()` L322-344 → 精确行号 ✓
- Task 2.1：新建 `tests/fixtures/wang2022/iss_i.json` → 包含完整 JSON 示例 ✓
- Task 2.3：新建 `tests/test_flowsheet/test_iss_i.py` → 5 个测试用例概述 ✓
- ✅ issue 清零

### R3 — 风险与边缘
- 检查：并行化、回滚安全、跨 Task 一致性
- **R3-1** 并行化：W4 内 T2.1 和 T2.2 可并行（独立修改 schema + solver）✓
- **R3-3** 回滚安全：Phase 1 为纯代码修改，git revert 即可 ✓
- **R3-5** 边界控制：T2.3 明确不依赖张世坤补数据 ✓
- **R3-7** What-If：如果 CD2_bottom 分流比例错误 → E1/E2 流量失衡 → 不收敛。缓解：可在 iss_i.json 的 splitter section 中手动调整 ratio
- **终止条件**：T2 — T2.3 全系统求解不收敛 → 标记 BLOCKED，等待后续调参

---

## 假设记录

1. `[假设: Equilibrator 温度 25 K 适用于 ISS-I]` — 从 .bkp 看 E1/E2 温度接近 25 K，但确切值由 B2-B6/B13-B15 决定。如果后续发现温度不合理，需从 .bkp 反算实际出口温度。
2. `[假设: CD2 底分流比约 50:50]` — 等待张世坤补数据中确认。如果误差大，需用迭代拟合或 Aspen 结果反推。
3. `[假设: 压缩机直通处理不影响组分分离]` — B13/B14/B15 只改变压力，对 isotope separation 的 direction 无影响。
