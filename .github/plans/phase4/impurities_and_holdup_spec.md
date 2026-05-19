# 学生任务：h2iso 杂质扩展 + 板效率/holdup 导出 信息收集与开发清单

**版本**: v0.1
**日期**: 2026-05-19
**发起人**: 张小康
**适用学生**: 张世坤（博士在读，主攻 ISS 与同位素分离方向，已熟悉 0-D 燃料循环建模）；备选 孙维（硕士，氚输运方向，可承接 holdup 子任务）
**预期投入**: 杂质扩展 ~ 4 周；板效率/holdup ~ 3 周（可并行）
**目标**: 为 h2iso 增加（A）非氢同位素杂质组分 与（B）板效率/holdup 导出能力，使其能驱动 tricys 的 ISS 模块达到工程级仿真精度。

---

## 缺口 A — 杂质扩展（CO / CH₄ / N₂ / He-3 / He-4）

聚变堆 TEP（Tritium Extraction Plant）来流含痕量碳氢与惰性气体，现有 h2iso 仅有 H₂/D₂/T₂/HD/HT/DT 六组分，无法描述杂质在 ISS 各塔的分配，影响下游 WDS/SDS 接口的氚浓度估算与吹扫策略。

### A.1 文献与物性数据收集

请按下表整理一份 Excel/CSV，每个物种一行，每个数据点附文献引用（DOI / 报告号 / 数据集 URL）。

| 数据项 | H₂ ref | CO | CH₄ | N₂ | He-3 | He-4 |
|--------|--------|----|-----|----|------|------|
| 三相点温度 T_tp [K] | 13.957 | ? | ? | ? | 不存在固相 | 不存在固相 |
| 三相点压力 P_tp [Pa] | 7041 | ? | ? | ? | — | — |
| 沸点 T_b @ 1 atm [K] | 20.28 | ? | ? | ? | 3.19 | 4.222 |
| 临界温度 T_c [K] | 32.94 | ? | ? | ? | 3.35 | 5.195 |
| 临界压力 P_c [bar] | 12.93 | ? | ? | ? | 1.165 | 2.275 |
| 偏心因子 ω | -0.218 | ? | ? | ? | ? | ? |
| 摩尔气化潜热 ΔH_vap [J/mol] @ T_b | ? | ? | ? | ? | ? | ? |
| Antoine A, B, C（低温段） | 已有 | ? | ? | ? | ? | ? |
| 与 H₂ 的 SRK 二元相互作用系数 kij | — | ? | ? | ? | ? | ? |
| 与 T₂ 的 SRK kij | — | ? | ? | ? | ? | ? |

**建议数据源**:
- NIST Chemistry WebBook（CO/CH₄/N₂/He 物性主源）
- Wang et al. 2022 *Fusion Eng. Des.* （ISS 杂质考虑章节）
- ITER ISS-1.0 设计文件（杂质包络）
- DIPPR 数据库（如学校能访问）
- 对 He-3：NIST + Souers 1986 关于氦同位素的章节

### A.2 工艺影响范围调研

需要回答以下问题（每条不少于 1 段文字 + 至少 1 篇支持文献）：

1. 在 ISS-I/O 各塔的典型操作温度（19–30 K）下，CO/CH₄/N₂ 是否会固化或部分固化？固化对塔器运行的影响（堵塞、结霜）是否需要在模型中考虑？
2. He-3（氚衰变产物）在 ISS 塔顶的累积速率估算（基于 T₂ holdup × 衰变常数）。
3. He-4 是否仅作为不凝气体直接走 vent，还是会在再沸器/冷凝器产生气阻？
4. ITER / EU-DEMO / CFEDR 现有设计文件中，杂质的进料浓度典型值（mol%）。

### A.3 代码修改清单（h2iso 侧，学生只起草、不直接合并）

需要修改的文件 / 接口（学生在 fork 上完成 PR）：

| 文件 | 修改内容 |
|------|---------|
| `src/h2iso/species.py` | 扩展 `SPECIES_ORDER` 到 11 组分；定义新 enum 与索引常量 |
| `src/h2iso/_data.py` | 新增 `IMPURITY_DATA` dict（A.1 表格内容） |
| `src/h2iso/vle/pvap.py` | 为 CO/CH₄/N₂/He 加入 Antoine 形式 pvap 函数；He-3/He-4 在常规操作温度下 P_sat > 操作压力，按 "永远全在气相"处理（K_i = ∞） |
| `src/h2iso/vle/rachford_rice.py` | 处理 K_i = ∞ 的退化情况：将该组分全部分配到气相，从 R-R 方程剔除后求解 |
| `src/h2iso/vle/srk.py` | 扩展 kij 矩阵；不凝气体特例 |
| `src/h2iso/mesh/column.py` | feed_composition 维度更新 |
| `tests/test_vle/test_impurity.py` | 新建，覆盖：低温 CO 沸点测试、He 不凝气体相分配测试、混合物 R-R 退化处理 |
| `tests/fixtures/` | 新增 1 个含 1% CO + 0.5% N₂ 的小 fixture |

### A.4 验收标准

- A.1 表格 100% 填充且每个数据点有引用。
- A.2 四个问题各有书面答复，**且** 附带至少 2 篇文献支撑全部回答。
- A.3 代码 PR 通过本地 `pytest -q`（≥ 全部 345 现有测试 + 新增不少于 10 个测试）。
- 杂质 fixture 在 CD2 单塔上仿真：塔顶 H₂ 纯度变化与无杂质 baseline 一致（受杂质稀释 < 0.5% 偏离）；杂质 99% 走塔顶 vent。

---

## 缺口 B — 板效率 / Holdup 导出

tricys 的 L3 黑箱 ISS 模型需要 holdup（持液/持气量）来正确描述瞬态响应，特别是启停、扰动追踪、氚滞留分析。当前 h2iso 仅做稳态求解，未导出 holdup；板效率（Murphree efficiency）目前固定 100%（理想塔板）。

### B.1 Murphree 板效率模型

请整理一份 ~10 页的 review 文档，覆盖以下内容：

1. Murphree efficiency 定义（液相 / 气相）及在氢同位素分离塔中的典型取值（参考 Souers 1986 第 12 章、Wang 2022）。
2. 半经验关联式（O'Connell、AIChE bubble-cap model）在低温窄沸点差体系下的适用性评估。
3. 推荐的工程值：建议给 h2iso 一个 species-pair-dependent Murphree 表（如 H₂-T₂ 0.85，H₂-D₂ 0.90 等）。

### B.2 Holdup 关联式

需要为以下两种塔器结构调研并整理 holdup 模型：

| 塔器类型 | 持液量模型 | 持气量模型 | 适用场景 |
|----------|-----------|-----------|---------|
| 板式塔（bubble-cap / sieve） | Bennett-Agrawal / Hofhuis-Zuiderweg | per stage volume × void fraction | ISS-I CD1, CD2 |
| 填料塔（packed） | Stichlmair / Bravo-Fair / Rocha-Bravo-Fair | 气相 < 5% 持气 | ISS-I CD3, ISS-O |

对每个模型，需要：
- 公式
- 输入需要的几何参数清单（塔径 D、板间距 H、孔率 α、填料类型与比表面积 a 等）
- 不确定性范围（±20% 是典型）
- Python 实现伪代码

### B.3 代码修改清单（h2iso 侧）

| 文件 | 修改内容 |
|------|---------|
| `src/h2iso/mesh/column.py` | `ColumnSpec` 增加 `geometry: ColumnGeometry`（新 dataclass：tray_type, D, H_tray, …） + `murphree_eff: dict[(int,int), float]` |
| `src/h2iso/mesh/holdup.py` | 新建模块，按 B.2 实现两套关联式 |
| `src/h2iso/mesh/efficiency.py` | 新建，Murphree 修正后 K_eff = K_eq × E |
| `src/h2iso/codegen/modelica_records.py` | 扩展模板，在 Modelica 初值中导出 `holdup_l_init[N]`, `holdup_v_init[N]`, `murphree_eff[N,N_species]` |
| `tests/test_mesh/test_holdup.py` | Bennett-Agrawal 与文献 worked example 对比 |
| `tests/test_mesh/test_efficiency.py` | Murphree=1 退化为理想塔板（与现有 fixture 一致） |
| `tests/fixtures/` | 现有 fixtures 增加 geometry 字段 |

### B.4 验收标准

- B.1 综述文档定稿，附 ≥ 15 篇文献。
- B.2 对每个塔型至少 1 个文献 worked example 可在 Python 实现下复现（相对误差 < 10%）。
- B.3 代码 PR 通过本地 `pytest -q`（≥ 全部现有测试 + 不少于 15 个新增测试）。
- Modelica 导出的初值 `.mos` 文件可被 tricys 中至少 1 个 ISS L3 模型成功加载并仿真 1000 s（不发散）。

---

## 协作流程

1. 接到本文档后，**第 1 周** 完成 A.1 + A.2 + B.1 数据收集与综述提纲，发我审阅。
2. 通过审阅后，**第 2-3 周** 完成 A.3 + B.2 + B.3 实现（在自己 fork 上）。
3. **第 4 周** 完成 A.4 + B.4 验收测试，发 PR 到主仓库（届时仓库会开放协作权限）。
4. PR review 期间，张小康负责 code review，宋江锋负责 ISS 工艺合理性审阅。
5. 合并后纳入 h2iso 主版本，相关贡献写入论文致谢与作者列表（学生第二/第三作者，依据贡献量）。

---

## 参考资料起点

- Souers P.C. (1986), *Hydrogen Properties for Fusion Energy*, UC-Press. 第 9 章蒸汽压、第 12 章塔效率。
- Wang J. et al. (2022), *Fusion Eng. Des.* — ISS 杂质章节。
- ITER ISS-1.0 设计文件（向 张小康 申请内部访问）。
- Kister H.Z. (1992), *Distillation Design*, McGraw-Hill — 第 14 章板效率、第 8 章 holdup。
- Stichlmair J., Fair J.R. (1998), *Distillation: Principles and Practice*, Wiley-VCH — 填料塔水力学。
- 现有 h2iso 仓库：（仓库在私有 GitHub，请向 张小康 申请协作邀请）

---

## 不要做什么（避免走弯路）

- ❌ 不要试图自己直接动 SRK kij 矩阵的数值——先把数据来源列清楚再讨论。
- ❌ 不要试图在 h2iso 内部加入催化反应器或动态相变模型——超出当前 scope。
- ❌ 不要使用未经审阅的 LLM 输出作为物性数据来源——所有数据必须可追溯到原始文献。
- ❌ 不要修改 `src/h2iso/codegen/` 之外的 codegen 路径，特别是 `src/h2iso/cli.py` 与 CI workflow，先与 张小康 讨论。
