# h2iso

**H**ydrogen **Iso**tope Thermodynamics — 开源氢同位素低温热力学与精馏求解器

## Overview

h2iso 提供氢同位素（H₂/HD/HT/D₂/DT/T₂）低温体系的：

- **L1-VLE 物性内核**：Souers 蒸汽压关联式、量子修正、K-value、BIP/kij 参数库
- **L2-CasADi 稳态 MESH 求解器**：高板数（15-100 理论板）精馏塔稳态求解
- **催化同位素交换平衡**：H₂+D₂⇌2HD 等反应的平衡组成计算
- **Modelica 初始化导出**：为 OpenModelica 动态塔模型提供可靠初值

## Installation

```bash
pip install h2iso              # 基础 VLE（仅 numpy/scipy）
pip install h2iso[solver]      # 含 CasADi MESH 求解器
pip install h2iso[dev]         # 开发依赖
```

## Quick Start

```python
from h2iso.vle import bubble_pressure, kvalue
from h2iso.mesh import Column

# VLE 计算
T = 22.0  # K
x = [0.0, 0.0, 0.0, 0.98, 0.02, 0.0]  # D2=98%, DT=2%
P, y = bubble_pressure(T, x)

# 精馏塔稳态求解
col = Column(
    n_stages=75,
    feed_stage=37,
    feed={"flow_mol_h": 80.357, "z": x, "T": T, "P": 90000},
    specs={"reflux_ratio": 15, "D_F": 0.979},
)
result = col.solve()
print(f"Top D2 purity: {result.x_profile[0, 3]:.6f}")
```

## Architecture

h2iso 是 [tricys](https://github.com/asipp-neutronics/tricys) 多保真精馏框架中的 L1+L2 层：

```
L0  文献/外部对标   ← Wang 2022, DWSIM, Aspen
L1  VLE 物性层      ← h2iso.vle        ⬅ THIS PACKAGE
L2  稳态 MESH 层    ← h2iso.mesh       ⬅ THIS PACKAGE
L3  Modelica 动态   ← tricys (OpenModelica)
L4  系统集成       ← tricys (OMPython + FOC)
L5  多保真应用     ← tricys config
```

## License

MIT
