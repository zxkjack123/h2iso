# Modelica 测试模型架构解析与测试套件说明

本目录 (`tests/modelica`) 包含了基于 `h2iso` 同位素分离严格计算内核导出的 Modelica 0-D 动态系统仿真模型与测试套件。用于聚变堆全厂燃料循环动态仿真、系统级集成验证及核安全分析。

---

## 1. 核心架构设计

整个 Modelica 测试套件采用 **物理机理核心 (Generic Core)** 与 **系统适配层 (Adapter Layer)** 解耦分层架构：

1. **纯物理核心 (`Generic_ISS.mo`)**：真实反映多组分（$H_2, HD, HT, D_2, DT, T_2$ 6 维分子）同位素在低温精馏塔 (CD) 和催化平衡反应器 (Equilibrator) 中的物理演化与质量传递，严格遵守组分守恒与热力学相平衡规律。
2. **系统应用适配层 (`Generic_ISS_Adapters.mo`)**：提供从宏观系统（如全同位素 5 维原子流、或 3LC 核安全三级包容 1 维标量氚流）到 6 维物理核心的双向等效映射与折算，实现即插即用集成。

---

## 2. Wang (2022) 通用机理组件设计 (`Generic_***`)

系统中的 `Generic_ISS.mo` 实现了标准化多柱串联氢同位素分离系统模型：

* **`Column_0D_6` (精馏塔降阶代理)**:
  - 控制方程基于一阶水力学滞后：$\dot{m}_{outflow,i} = I_i / \tau$；
  - 动态微分质量守恒：$\frac{d I_i}{dt} = \dot{m}_{feed,i} - \dot{m}_{outflow,i}$；
  - 分离比 ($SF$) 参数由 `h2iso` 高保真稳态 MESHL 方程组求解获得，支持通过参数覆盖文件动态注入。
* **`Equilibrator_0D_6` (催化交换平衡反应器)**:
  - 模拟催化床上的统计同位素交换行为；
  - 将输入分子打散为 H、D、T 原子流，按同位素统计二项分布重组分配出 6 种分子，保证原子绝对守恒。
* **`ISS_I_Core` 与 `ISS_O_Core`**:
  - 分别对应内燃料循环 (4 塔 + 2 平衡器) 与外燃料循环 (3 塔 + 1 平衡器) 的通用网络拓扑。

---

## 3. 适配器 (Adapter Layer) 设计

适配器隔离了底层机理逻辑与顶层系统接口协议，实现维度无损升降变换与核安全审计：

* **接口升维 (映射入 Core)**：
  - 标量氚流（1D）或原子流（5D）根据等离子体排气（$D:T=1:1$）或增殖流（$a_H \approx 0.99, a_T \approx 0.01$）丰度重构为 6 维分子进料。
* **接口降维 (输出至 System)**：
  - 提取高纯产品流与脱氢废气流，按各分子中氚原子的质量分数加权折算为系统级产氚信号（如送入 SDS 储氚系统）。
* **核安全边界审计**：
  - 内嵌 3-Level Confinement (3LC) 泄漏模型，按系统通量实时计算向次级包容环路及通风除氚系统 (VDS) 的微量渗透。

---

## 4. 子测试目录与用例说明

| 子测试目录 | 接口维度 | 测试目标与系统模型 | 对应测试报告 |
| :--- | :--- | :--- | :--- |
| **[`vector_5d_mapping/`](vector_5d_mapping/)** | 5 维原子向量流 `[T, D, H, He, Imp]` | 全同位素原子追踪验证，集成于全厂燃料闭环模型 `example_model.mo` | [REPORT.md](vector_5d_mapping/REPORT.md) |
| **[`scalar_1d_mapping/`](scalar_1d_mapping/)** | 1 维标量纯氚流 `m_T (g/h)` | CFEDR 2870 MW (3LC) 全厂三级包容与核安全验证，模型 `CFEDR_2870_3lc_ssp.mo` | [REPORT.md](scalar_1d_mapping/REPORT.md) |

每个子目录下均包含：
- 独立的 OpenModelica 执行脚本 (`simulate_*.mos`)；
- 一键自动化测试与验证工具 (`run_simulation.py`)；
- 5000 小时动态响应轨迹分析与可视化图表 (`comparison_chart.png`)；
- 详细的技术分析报告 (`REPORT.md`)。

---

## 5. 参数覆盖文件 (`override_cycle.txt`) 生成工具

系统提供了专用的参数提取与代码生成脚本 [`generate_overrides.py`](generate_overrides.py)，用于从 `h2iso` 严格机理求解结果中提取精细分离比 ($SF$)、进出口温度 ($T$) 及滞留时间 ($\tau$)，并生成 Modelica 仿真所需的覆盖文件：

```bash
# 1. 基于基准算例直接生成并同步至各子测试目录
python generate_overrides.py

# 2. 调用 h2iso 严格流程求解器实时计算后再生成覆盖参数
python generate_overrides.py --solve

# 3. 指定输出目录
python generate_overrides.py --target-dir ./scalar_1d_mapping
```

