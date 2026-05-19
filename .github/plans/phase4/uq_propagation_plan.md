# h2iso 不确定性传播 (UQ) 实施方案

**版本**: v0.1
**日期**: 2026-05-19
**负责人**: 张小康
**目标**: 为 h2iso 增加一套可复现的不确定性传播框架，使所有发布结果（产品组成、再沸器/冷凝器热负荷、分离因子）附带置信区间，论文与 tricys 数字孪生均能引用。

---

## 1 范围与定位

- **目标量 QoI**：每个塔的 ①塔顶/塔底产品组成（六组分摩尔分数）、②再沸器与冷凝器热负荷、③分离因子 α、④收敛迭代数（衡量稳健性）。
- **不确定性源**：见 §3。
- **不在本方案范围**：催化反应器、动态相变、放射性衰变链——这些进入未来工作。
- **复用约束**：UQ 包裹层必须复用 h2iso 现有 `flowsheet.solve()` 入口，不修改 MESH 内核。

---

## 2 方法选择

| 方法 | 计算量 | 给出什么 | 适用阶段 |
|------|-------|---------|---------|
| 一阶 Sobol 灵敏度（SALib） | ~ N×(2K+2) 次仿真，K=参数数 | 主效应 + 总效应指数 | 第一轮筛选关键参数 |
| Monte Carlo + LHS | ~ 1000–10000 次仿真 | 完整分布、置信区间 | 第二轮量化（论文用） |
| PCE (polynomial chaos)，via chaospy | ~ 50–500 次仿真 | 近似分布 + 灵敏度 | 计算预算紧时备选 |

**推荐路线**：先用 SALib 做 100–500 次低成本扫描筛选出 top-K 关键参数（K≤8）；再对这些参数做 LHS Monte Carlo (N≥2000) 给出最终置信区间。PCE 仅在 MC 太慢时启用。

---

## 3 参数不确定性清单（输入空间）

| ID | 参数 | 类型 | 分布 | 来源/依据 |
|----|------|------|------|----------|
| P01 | Souers 锚定 T_tp（每个物种） | 物性 | Normal, σ=0.02 K | Souers 1986 误差棒 |
| P02 | Souers 锚定 P_tp（每个物种） | 物性 | Lognormal, σ_ln=0.02 | 同上 |
| P03 | ΔH_vap 校正系数 | 物性 | Uniform [0.97, 1.03] | 文献分散度 |
| P04 | SRK 二元交互参数 kij | 物性 | Normal, σ=0.01（绝对） | Wang 2022 拟合残差 |
| P05 | 氚量子修正幅度 | 物性 | Uniform [0.9, 1.1] × baseline | 文献分歧度 |
| P06 | 回流比 R | 操作 | Normal, σ=2% × baseline | 实测控制精度 |
| P07 | 进料流量 F | 操作 | Normal, σ=1% × baseline | 流量计精度 |
| P08 | 进料组成 z_i | 操作 | Dirichlet, α 与 z 一致，cv=5% | TEP 分析误差 |
| P09 | 操作压力 P | 操作 | Normal, σ=0.5 kPa | 压力控制精度 |
| P10 | Murphree 板效率（缺口 B 加入后） | 模型 | Uniform [0.7, 1.0] | 工程包络 |
| P11 | Holdup 关联式系数（缺口 B 加入后） | 模型 | Uniform ±20% | 文献分散度 |

P10–P11 在缺口 B 完成后再加入。当前 v0.1 范围：P01–P09，共 9 类参数（实际单参数计：约 6 物种 × 几个物性 + 操作参数 ≈ 20–30 个标量）。

---

## 4 代码实现

### 4.1 新模块 `src/h2iso/uq/`

```
src/h2iso/uq/
├── __init__.py
├── distributions.py    # 参数分布定义（包装 scipy.stats）
├── sampler.py          # SALib + LHS 包装
├── runner.py           # 并行调用 flowsheet.solve()，处理失败
├── qoi.py              # 从 flowsheet result 中抽取 QoI 向量
├── sobol.py            # Sobol 指数后处理
├── plot.py             # 不确定性带、tornado、Sobol 条形图
└── report.py           # 输出 UQ markdown 报告 + CSV
```

### 4.2 核心 API（草案）

```python
from h2iso.uq import UQStudy, ParameterSpace, qoi_default

space = ParameterSpace.from_yaml("uq_params.yaml")  # see §3
study = UQStudy(
    flowsheet_factory=build_iss_o_flowsheet,   # closure that returns Flowsheet
    parameter_space=space,
    qoi_fn=qoi_default,                        # default extracts §1 QoIs
)

# Step 1: SALib screening
sobol = study.run_sobol(n_base=128, seed=42, parallel=8)
sobol.save_report("uq_screening.md")

# Step 2: LHS Monte Carlo on top-K parameters
top_k = sobol.top_k(k=8, metric="ST")
mc = study.run_monte_carlo(
    n=2000,
    parameters=top_k,
    seed=42,
    parallel=8,
)
mc.save_report("uq_mc.md")
mc.save_csv("uq_mc.csv")
mc.plot_uncertainty_band("uq_mc.png")
```

### 4.3 并行与失败处理

- 使用 `concurrent.futures.ProcessPoolExecutor`，单次仿真独立沙箱。
- 每次仿真 wall-time 上限（默认 60 s），超时算 fail。
- 失败样本记录到 `uq_failures.jsonl`，统计 fail rate；若 fail rate > 5% 视为 UQ 失败需先稳健化。

### 4.4 与现有 h2iso 的接口

- 不修改 `flowsheet.solve()` 签名。
- 通过 `dataclasses.replace()` 在传入前 perturb `ColumnSpec` / `EquilibratorSpec` / 物性常量副本。
- 物性扰动通过 `h2iso.uq.context.set_property_overrides(dict)` 上下文管理器实现（线程局部），避免污染全局状态。

---

## 5 测试金字塔

| 层级 | 测试内容 | 数量目标 |
|------|---------|---------|
| 单元 | 分布采样器（边界、种子可复现）、QoI 提取器、Sobol 计算 | 20+ |
| 集成 | 一个小塔（N=10）做 SALib N_base=8 跑通；MC N=20 跑通 | 5+ |
| 回归 | 固定 seed 的 Sobol 指数与基准 JSON 对比（容忍 ±5%） | 2-3 |
| benchmark | 1 个 MC N=100 的端到端时间基准 | 1 |

---

## 6 验证案例

### 6.1 Wang 2022 CD2 单塔

- 9 类参数全开
- N_screen=128，N_mc=2000
- 输出：4 个 QoI 的 mean ± 95% CI + Sobol 条形图
- 目标：复现 Wang 2022 报告的 ±2% 实验范围（与本文 §3 比较）

### 6.2 ISS-O 三塔级联

- 同上参数集 + 撕裂流参数 q-factor（额外引入 1 个）
- 重点观察 Wegstein 迭代数的不确定性（衡量稳健性）

### 6.3（计划）ISS-I 三塔级联

- 等张世坤补齐工艺参数（参见 `phase4/iss_i_data_gap.md`）
- 与论文同期发布

---

## 7 输出与发布

每次 UQ run 产生一个独立目录 `uq_runs/<timestamp>/`，包含：

- `config.yaml`（参数空间 + 样本数 + seed）
- `samples.csv`（采样矩阵）
- `qoi.csv`（每次仿真的 QoI）
- `report.md`（markdown 报告，含主图、汇总表）
- `*.png`（不确定性带、tornado、Sobol）
- `failures.jsonl`（失败样本）

主仓库 `docs/uq/` 留存 1-2 个 canonical reference run，供论文与 tricys 数字孪生引用。

---

## 8 计算资源估算

- 单次 CD2 仿真：~ 1 s（CasADi + IPOPT）
- 单次 ISS-O 三塔仿真：~ 5 s（含 Wegstein）
- Sobol screening N_base=128，K=20 参数 → ~5000 次评估 → 8 并行 ~ 1 小时
- MC N=2000 全开 → ~ 7000 s 串行，8 并行 ~ 15 分钟

→ 本地一台机器即可完成，无需 HPC。

---

## 9 里程碑

| 里程碑 | 触发条件 |
|--------|---------|
| U1 框架就绪 | §4 模块全部代码 + §5 单元/集成测试通过 |
| U2 单塔验证 | §6.1 报告产出 |
| U3 多塔验证 | §6.2 报告产出 |
| U4 论文集成 | UQ 结果纳入论文 §3 Validation 与 §4 Discussion |

---

## 10 与论文 / tricys 的耦合

- **论文方面**：在 §3 Validation 的每个误差表格旁附加 95% CI（来自 §6.1/6.2）；§4 Discussion 加一个 "Sources of variability" 小节用 Sobol 指数解释。
- **tricys 数字孪生方面**：将 §6 输出的 QoI 分布作为 tricys 在线对齐模块的先验分布；缩短 Phase3 中描述的"参数后验更新"步骤。

---

## 11 风险与备选

| 风险 | 缓解 |
|------|------|
| SALib 在退化分布（如 P_tp 极窄 σ）时灵敏度数值不稳 | 在 sampler 中加入参数标准化与下界保护 |
| Wegstein 在边缘扰动下发散，fail rate 偏高 | 先做稳健化（Phase 3 已部分完成），UQ run 前要求 baseline 通过 |
| MC 2000 个样本仍欠采样多模态分布 | 升级到分层抽样 / 检查直方图重尾；必要时切到 PCE |
| 论文 reviewer 要求 GUM-style 不确定性表 | report 模板提供 GUM 列（k=2 扩展不确定度） |

---

## 12 不要做什么

- ❌ 不要在 MESH 内核里 inline UQ 调用——保持 separation of concerns。
- ❌ 不要把 UQ 当成参数辨识——本方案只做 forward propagation，参数辨识属于 tricys 数字孪生范畴。
- ❌ 不要发布缺少 seed / config / sample CSV 的 UQ 结果——可复现性强制约束。
