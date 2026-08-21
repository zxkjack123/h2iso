# 全同位素 5 维原子流映射与同位素分离系统测试 (example_model.mo)

本目录用于测试与验证 **`Generic_ISS` 物理核心库** 与 **`Generic_ISS_Adapters` 多组分适配层** 在全厂聚变燃料循环模型 **`example_model.mo`** 中的集成与 5000 小时动态长周期仿真。

---

## 一、 核心文件与结构

```text
h2iso/tests/modelica/vector_5d_mapping/
├── Generic_ISS.mo                  # 6 组分分子基准机理核心库 (Wang 2022 级联)
├── Generic_ISS_Adapters.mo         # 5 维原子流 [T,D,H,He,Imp] <-> 6 维分子流双向映射适配器
├── example_model.mo                # 全厂燃料循环闭环模型 (实例化 ISS_I_Adapter 与 ISS_O_Adapter)
├── override_cycle.txt              # h2iso 稳态高保真参数覆盖文件 (注入 o_iss.core.* 与 i_iss.core.*)
├── simulate_cycle.mos              # OpenModelica 5000h 动态闭环仿真执行脚本
├── run_simulation.py               # 一键仿真执行与绘图脚本
├── plot_results.py                 # 动态响应轨迹与稳态统计分析脚本
├── simulation_results_cycle_res.csv# 5000h 动态仿真输出数据
├── comparison_chart.png            # 仿真轨迹可视化分析图
├── README.md                       # 本说明指南
└── REPORT.md                       # 5000h 集成测试与多组分物理分析报告
```

---

## 二、 集成验证机制

### 1. 模型接入方式
在 [example_model.mo](example_model.mo) 中：
```modelica
model O_ISS "基于 Generic_ISS 的高保真 0-D ISS-O 物理模型与适配器"
  extends Generic_ISS_Adapters.ISS_O_Adapter;
end O_ISS;

model I_ISS "基于 Generic_ISS 的高保真 0-D ISS-I 物理模型与适配器"
  extends Generic_ISS_Adapters.ISS_I_Adapter;
equation
  from_NBI = {0, 0, 0, 0, 0};
end I_ISS;
```

### 2. 仿真执行流程
在 [simulate_cycle.mos](simulate_cycle.mos) 中按依赖顺序载入并仿真：
```modelica
loadFile("Generic_ISS.mo");
loadFile("Generic_ISS_Adapters.mo");
loadFile("example_model.mo");

simulate(
  example_model.Cycle,
  startTime = 0,
  stopTime = 5000,
  numberOfIntervals = 500,
  tolerance = 1e-6,
  method = "dassl",
  outputFormat = "csv",
  simflags = "-overrideFile override_cycle.txt",
  fileNamePrefix = "simulation_results_cycle",
  variableFilter = "time|sds\\.I\\[1\\]|o_iss\\.to_SDS\\[1\\]|i_iss\\.to_SDS\\[1\\]|wds\\.to_O_ISS\\[1\\]|tes\\.to_O_ISS\\[1\\]"
);
```

---

## 三、 快速验证步骤

### 运行一键验证命令
```bash
# 位于 h2iso/tests/modelica/vector_5d_mapping 目录下
python run_simulation.py
```
* 自动调用 OpenModelica (`omc`) 编译求解 `example_model.Cycle`；
* 自动输出稳态关键物理指标；
* 生成 [comparison_chart.png](comparison_chart.png) 轨迹图；
* 详细测试数据与分析见 [REPORT.md](REPORT.md)。
