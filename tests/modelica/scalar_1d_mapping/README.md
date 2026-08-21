# CFEDR 2870 MW (3-Level Confinement) 标量同位素分离系统测试

本目录用于测试与验证 **`Generic_ISS` 6 组分分子物理核心库** 与 **`Generic_ISS_Adapters` 3LC 标量适配层** 在聚变堆三级包容闭环模型 **`CFEDR_2870_3lc_ssp.mo`** 中的集成与 5000 小时动态长周期仿真。

---

## 一、 文件清单

```text
h2iso/tests/modelica/scalar_1d_mapping/
├── CFEDR_2870_3lc_ssp.mo           # CFEDR 2870 MW 全厂燃料循环与三级包容闭环模型 (集成 ISS 适配器)
├── Generic_ISS.mo                  # 6 组分分子机理核心库 (Wang 2022 纯机理)
├── Generic_ISS_Adapters.mo         # 3LC 标量适配器库 (含 ISS_I_3LC_Adapter 与 ISS_O_3LC_Adapter)
├── override_cycle.txt              # h2iso 稳态精细分离比与停留时间覆盖参数
├── simulate_ssp.mos                # OpenModelica 5000h 动态仿真脚本
├── run_simulation.py               # 一键仿真与绘图自动化执行器
├── plot_results.py                 # 4 面板动态轨迹分析与稳态统计脚本
├── simulation_results_ssp_res.csv  # 5000h 仿真输出数据
├── comparison_chart.png            # 4 面板高清轨迹图表 (symlog 对数坐标)
├── README.md                       # 本说明文档
└── REPORT.md                       # 5000h 闭环测试与核安全分析报告
```

---

## 二、 3LC 适配器集成架构

### 1. 物理映射与质量守恒
* **进料重构（1D 标量 $\rightarrow$ 6 维分子）**：
  * **I-ISS 进料（TEP）**：根据等摩尔 $D-T$ 排气假设，将进料标量氚流 $m_T$ 分配为 $[D_2, DT, T_2]$ 分子流，严格保持进料氚质量守恒：
    $$m_{T, in} = \dot{m}_{DT}\frac{M_T}{MW_{DT}} + \dot{m}_{T2} \equiv m_T$$
  * **O-ISS 进料（TES/WDS/CPS）**：将进料微量氚融入超轻氢气载体（$a_H \approx 0.99, a_T \approx 0.01$），保持进料纯氚当量严格守恒。
* **出料折算（6 维分子 $\rightarrow$ 1D 标量）**：
  * 对 `prod_T2_SDS` 和 `waste_HD` 分子流进行精确原子质量加权求和，输出纯氚产物流 `to_SDS` 与脱氢废气流 `to_WDS`。
* **三级包容（3LC）安全审计**：
  * 内置微量动态渗透泄漏接口 `to_VDS` 与 `to_Secondary`，严格匹配 CFEDR 核安全包容环路。

### 2. 模型接入方式
```modelica
  model O_ISS "Outer Isotope Separation System based on Generic_ISS_Adapters"
    extends Generic_ISS_Adapters.ISS_O_3LC_Adapter;
  end O_ISS;

  model I_ISS "Inner Isotope Separation System based on Generic_ISS_Adapters"
    extends Generic_ISS_Adapters.ISS_I_3LC_Adapter;
  end I_ISS;
```

---

## 三、 快速运行与验证

```bash
# 位于 h2iso/tests/modelica/scalar_1d_mapping 目录下
python run_simulation.py
```
* 自动调用 OpenModelica (`omc`) 编译求解 `CFEDR_3LC.Cycle_3LC`；
* 自动输出稳态关键物理指标；
* 生成 [comparison_chart.png](comparison_chart.png) 轨迹图；
* 详细测试数据与分析见 [REPORT.md](REPORT.md)。
