# CD2 UQ Validation Report

## Overview

This report documents the uncertainty propagation (UQ) study on the
Wang 2022 ISS-I CD2 distillation column using the h2iso UQ framework.

## Setup

### Column Configuration

| Parameter | Value | Source |
|-----------|-------|--------|
| Stages | 75 | Wang 2022 Table 5 |
| Feed stage | 37 | Wang 2022 Table 5 |
| Reflux ratio | 15 | Wang 2022 Table 5 |
| D/F | 0.979 | Wang 2022 Table 5 |
| Pressure | 90–100 kPa | Wang 2022 Table 5 |
| Feed flow | 80.357 mol/h | Wang 2022 Table 1 |
| Feed composition | D2=98%, DT=2% | Wang 2022 Table 1 |

### UQ Parameters (Operational Subset P06–P09)

| ID | Parameter | Distribution | σ | Bounds | Description |
|----|-----------|-------------|---|--------|-------------|
| P06 | reflux_ratio | Normal | 2% × 15 = 0.3 | [7.5, 30] | Control precision |
| P07 | feed_flow | Normal | 1% × 80.357 = 0.804 | [40, 120] | Flow meter accuracy |
| P08 | z_D2 | Normal | 5% × 0.98 = 0.049 | [0.5, 0.999] | TEP analysis error |
| P09 | pressure | Normal | 500 Pa | [80k, 110k] | Pressure control |

## Running

### Fast test (15-stage, ~30s)

```bash
python -m h2iso.uq.run_cd2
```

### Canonical validation (75-stage, ~30min)

```bash
python -m h2iso.uq.run_cd2 --full --parallel 4
```

### Custom parameters

```bash
python -m h2iso.uq.run_cd2 --mc-n 500 --sobol-n 32 --seed 123
```

## Expected Outputs

Each run produces a directory `uq_runs/cd2/n{N}_seed{S}/mc/` containing:

- `report.md` — Markdown report with QoI statistics and Sobol indices
- `samples.csv` — Converged sample matrix + QoI values
- `failures.jsonl` — Failed sample details (if any)

## Key Results (15-stage fast run, seed=42)

### Sobol Sensitivity (n_base=32, 192 samples, 0% fail)

Top-3 parameters by total-order Sobol index:

| QoI | #1 | #2 | #3 |
|-----|----|----|-----|
| x_top[D2] | z_D2 | pressure | reflux_ratio |
| x_bot[DT] | z_D2 | pressure | reflux_ratio |
| Q_condenser | reflux_ratio | feed_flow | z_D2 |
| T_top | pressure | z_D2 | reflux_ratio |

**Interpretation**: Feed composition (z_D2) dominates product purity QoIs,
reflux ratio dominates heat duty, and pressure dominates temperature —
all physically expected for a cryogenic distillation column.

### Monte Carlo (n=200, 0% fail)

| QoI | Mean | Std | 95% CI |
|-----|------|-----|--------|
| x_top[D2] | 0.9729 | 0.031 | [0.897, 0.999] |
| x_top[DT] | 0.0271 | 0.031 | [0.001, 0.103] |
| x_bot[D2] | 0.7572 | 0.222 | [0.350, 0.987] |
| x_bot[DT] | 0.2428 | 0.222 | [0.013, 0.650] |
| Q_condenser (W) | -430.7 | 9.3 | [-447, -410] |
| Q_reboiler (W) | 441.9 | 14.7 | [417, 471] |
| T_top (K) | 23.46 | 0.027 | [23.42, 23.51] |
| T_bottom (K) | 23.60 | 0.154 | [23.42, 23.89] |

## Future Work

- **Property parameter perturbation (P01-P05)**: Implemented in `src/h2iso/uq/properties.py`.
  Use `Parameter("souers.D2.C1", "normal", ...)` in the parameter space and the
  runner automatically applies global overrides during each solve.
- **ISS-O multi-column UQ**: Implemented in `src/h2iso/uq/run_isso.py`.
  `python -m h2iso.uq.run_isso` for fast (no-recycle, 12-stage) CI mode.
  `python -m h2iso.uq.run_isso --full` for full ISS-O with recycles.
- **ISS-I CD1+CD3 validation**: Blocked on CFEDR parameter data (see
  `iss_i_data_gap.md`).
