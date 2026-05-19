# MESH Solver API Reference

## `h2iso.mesh.column` — Column Solver

### `ColumnSpec` dataclass

Column specification for the MESH solver.

```python
from h2iso.mesh import ColumnSpec

spec = ColumnSpec(
    n_stages=75,
    feed_stage=37,
    feed_flow=80.357,       # mol/h
    feed_composition=feed,  # ndarray shape (6,)
    pressure=90_000,        # Pa
    reflux_ratio=15.0,
    distillate_to_feed=0.979,
    feed_quality=1.0,       # 1.0 = saturated liquid (default)
)
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `n_stages` | int | Total number of theoretical stages (including condenser/reboiler) |
| `feed_stage` | int | Feed stage index (0-based, 0=condenser) |
| `feed_flow` | float | Feed molar flow rate (mol/h) |
| `feed_composition` | ndarray | Feed mole fractions, shape (6,), must sum to 1 |
| `pressure` | float | Column pressure (Pa), assumed constant |
| `reflux_ratio` | float | External reflux ratio L/D |
| `distillate_to_feed` | float | Distillate-to-feed ratio D/F |
| `feed_quality` | float | Feed thermal condition (1.0 = saturated liquid) |

### `Column` class

```python
from h2iso.mesh import Column

col = Column(spec)
nlp = col.build_nlp()
result = col.solve()
```

**Methods:**

- `build_nlp()` → dict: Construct CasADi NLP problem (variables, constraints, bounds)
- `solve()` → `ColumnResult`: Solve the NLP with IPOPT and extract profiles

### `ColumnResult` dataclass

Solution container returned by `Column.solve()`.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `T_profile` | ndarray (N,) | Temperature at each stage (K) |
| `x_profile` | ndarray (N, 6) | Liquid mole fractions at each stage |
| `y_profile` | ndarray (N, 6) | Vapor mole fractions at each stage |
| `L_profile` | ndarray (N,) | Liquid flow rate at each stage (mol/h) |
| `V_profile` | ndarray (N,) | Vapor flow rate at each stage (mol/h) |
| `condenser_duty` | float | Condenser heat duty (W, negative = cooling) |
| `reboiler_duty` | float | Reboiler heat duty (W, positive = heating) |
| `convergence_info` | dict | Solver diagnostics (status, iterations, success) |

---

## `h2iso.mesh.continuation` — Continuation Solver

For columns with >30 stages, direct NLP solve often fails. The continuation
solver builds up from a smaller column using warm-start interpolation.

### `ContinuationSolver` class

```python
from h2iso.mesh import ContinuationSolver

solver = ContinuationSolver()
solver.add_step("N", target=30, n_substeps=1)
solver.add_step("N", target=75, n_substeps=3)
result = solver.solve(spec)
```

**Methods:**

- `add_step(param, target, n_substeps=1)`: Add a continuation step
  - `param`: Parameter to vary — `"N"` (stages), `"R"` (reflux), `"DF"` (D/F ratio)
  - `target`: Target value for the parameter
  - `n_substeps`: Number of intermediate steps (linear interpolation)
- `solve(base_spec)` → `ContinuationResult`: Execute the full continuation path

### `ContinuationResult`

**Fields:**

- `final`: The `ColumnResult` at the last continuation step
- `history`: List of intermediate `ColumnResult` objects
- `steps`: List of step descriptions

---

## `h2iso.mesh.export` — Profile Export

### `export_csv(result, path)`

Export column profiles to CSV format.

```python
from h2iso.mesh.export import export_csv
export_csv(result, "profiles.csv")
```

Columns: `stage, T, x_H2, x_HD, x_HT, x_D2, x_DT, x_T2, y_H2, ..., y_T2, L, V`

### `export_json(result, path)`

Export column profiles to JSON format.

```python
from h2iso.mesh.export import export_json
export_json(result, "profiles.json")
```

### `export_mat(result, path)`

Export to MATLAB v4 `.mat` format.

```python
from h2iso.mesh.export import export_mat
export_mat(result, "profiles.mat")
```

---

## `h2iso.mesh.stage` — Single Stage

### `Stage` class

Single equilibrium stage solver (used internally and for debugging).

```python
from h2iso.mesh import Stage

stage = Stage(T_guess=24.0, P=90_000, x_feed=feed)
T_eq, x_eq, y_eq = stage.solve()
```

---

## `h2iso.codegen.modelica_init` — Modelica Initialization

### `generate_init_script(result, model_name)`

Generate an OpenModelica `.mos` initialization script from column profiles.

```python
from h2iso.codegen.modelica_init import generate_init_script

mos = generate_init_script(result, model_name="CD2_Column")
with open("init_cd2.mos", "w") as f:
    f.write(mos)
```

**Parameters:**

- `result` (ColumnResult): Solved column result
- `model_name` (str): Modelica model qualified name

**Returns:** String content of the `.mos` script.
