# Quick Start

Solve a 75-stage D₂/DT cryogenic distillation column in under 5 minutes.

## Prerequisites

```bash
pip install h2iso[solver]
```

## Step 1: Define Feed

```python
import numpy as np
from h2iso.mesh import ColumnSpec, ContinuationSolver

# 6-component composition: [H2, HD, HT, D2, DT, T2]
feed = np.zeros(6)
feed[3] = 0.98  # D2 = 98%
feed[4] = 0.02  # DT = 2%
```

## Step 2: Create Column Specification

```python
spec = ColumnSpec(
    n_stages=15,            # Start small for warm-start
    feed_stage=8,           # Feed at middle
    feed_flow=80.357,       # mol/h
    feed_composition=feed,
    pressure=90_000,        # Pa (90 kPa)
    reflux_ratio=15,
    distillate_to_feed=0.979,
)
```

## Step 3: Solve with Continuation

For high stage counts (>30), use the continuation solver to build up from a
smaller column:

```python
solver = ContinuationSolver()
solver.add_step("N", target=30, n_substeps=1)   # 15 → 30 stages
solver.add_step("N", target=75, n_substeps=3)   # 30 → 45 → 60 → 75

result = solver.solve(spec)
col = result.final  # ColumnResult for the 75-stage column
```

## Step 4: Inspect Results

```python
print(f"Top D2 purity:  {col.x_profile[0, 3]:.4%}")
print(f"Top DT:         {col.x_profile[0, 4]:.6%}")
print(f"Bottom DT:      {col.x_profile[-1, 4]:.4%}")
print(f"T_top:          {col.T_profile[0]:.2f} K")
print(f"T_bottom:       {col.T_profile[-1]:.2f} K")
print(f"Condenser duty: {col.condenser_duty:.1f} W")
print(f"Reboiler duty:  {col.reboiler_duty:.1f} W")
```

Expected output:

```
Top D2 purity:  99.9966%
Top DT:         0.003400%
Bottom DT:      95.0780%
T_top:          23.26 K
T_bottom:       23.93 K
Condenser duty: -429.7 W
Reboiler duty:  479.1 W
```

## Step 5: Export Profiles

```python
from h2iso.mesh.export import export_csv, export_json

export_csv(col, "cd2_profiles.csv")
export_json(col, "cd2_profiles.json")
```

## Step 6: Generate Modelica Initialization (Optional)

```python
from h2iso.codegen.modelica_init import generate_init_script

mos_content = generate_init_script(col, model_name="CD2_Column")
with open("init_cd2.mos", "w") as f:
    f.write(mos_content)
```

## VLE-Only Usage

If you only need thermodynamic properties without the column solver:

```python
from h2iso.vle.souers import pvap
from h2iso.vle.mixing import kvalue, bubble_pressure

# Pure component vapor pressure
P_D2 = pvap(24.0, "D2")  # Pa at 24 K

# K-values for a mixture at T=24K, P=90kPa
x = np.array([0, 0, 0, 0.98, 0.02, 0])
K = kvalue(24.0, 90_000, x)

# Bubble pressure
P_bub = bubble_pressure(24.0, x)
```

## Next Steps

- [VLE API Reference](api/vle.md) for full property function documentation
- [MESH API Reference](api/mesh.md) for solver configuration options
- [Validation Report](validation/mesh_report.md) for benchmark comparisons
