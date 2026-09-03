# ISS-I Four-Column Validation Report

## Reference

X. Wang et al., "Hydrogen isotope inventory evaluation of hydrogen isotopes
separation system of CFETR using Aspen Plus simulator", *Fusion Engineering
and Design*, vol. 184, 2022, doi: 10.1016/j.fusengdes.2022.113078.

## System Description

ISS-I (inner fuel cycle) four-column cryogenic distillation cascade with two catalytic equilibrators:

- **CD1**: 90 stages, R=50, D/F=0.185 — separates D₂/HD/HT from DT/T₂
- **CD2**: 75 stages, R=15, D/F=0.979 — purifies NBI D₂ feed
- **CD3**: 100 stages, R=60, D/F=0.780 — concentrates high-purity T₂ bottom product
- **CD4**: 60 stages, R=295, D/F=0.0328 — separates HD overhead exhaust from D₂ product

### Interconnections & Topology:
- **TEP Feed** (22.32 mol/h: H₂ 0.014%, HD 1.058%, HT 0.94%, D₂ 24.778%, DT 48.43%, T₂ 24.78%) → CD1 stage 50
- **NBI Feed** (80.357 mol/h: D₂ 98.0%, DT 2.0%) → CD2 stage 37
- **CD1 bottom** (DT/T₂ rich) → CD3 stage 45
- **CD2 bottom** (DT rich) → CD3 stage 15
- **CD1 top** (D₂/HD/HT) → **Equilibrator 2 (E2)** (2HT ⇌ H₂ + T₂, HT + D₂ ⇌ HD + DT) → CD4 stage 55
- **CD3 top** (DT rich) → **Equilibrator 1 (E1)** (2DT ⇌ D₂ + T₂) → CD1 stage 72 (**Recycle Tear Stream**)
- **Products**:
  - `CD2_distillate`: High-purity D₂ (>99.97%)
  - `CD3_bottoms`: High-purity T₂ (>95.5%)
  - `CD4_bottoms`: Recovered D₂ product (>97.7%)
  - `CD4_distillate`: HD overhead exhaust (>98.8%)

## Solver Configuration

- Method: Sequential Modular with Wegstein acceleration
- Continuation substeps: 3 (warm-start from 15 stages)
- Convergence tolerance: 1×10⁻⁴ on tear stream composition

## Results

### Convergence

| Metric | Value |
|--------|-------|
| Converged | Yes |
| Iterations | 18 |
| Final tear residual | 4.98×10⁻⁶ |

### Temperature Comparison (K)

| Column | Position | h2iso | Wang 2022 | Δ (K) |
|--------|----------|-------|-----------|-------|
| CD1 | Top | 23.39 | 23.37 | +0.02 |
| CD1 | Bottom | 24.13 | 24.51 | −0.38 |
| CD2 | Top | 23.44 | 23.41 | +0.03 |
| CD2 | Bottom | 24.12 | 24.41 | −0.29 |
| CD3 | Top | 23.96 | 24.12 | −0.16 |
| CD3 | Bottom | 24.78 | 24.61 | +0.17 |
| CD4 | Top | 21.88 | 21.83 | +0.05 |
| CD4 | Bottom | 23.44 | 23.79 | −0.35 |

All temperature deviations are < 0.4 K, well within the 2.0 K acceptance criteria.

### Product Composition Comparison

| Product Stream | Target Component | h2iso | Wang 2022 | Status |
|----------------|------------------|-------|-----------|--------|
| CD2 Top (Distillate) | D₂ purity | 99.99% | 99.97% | ✅ PASS |
| CD3 Bottom | T₂ purity | 95.55% | 93.36% | ✅ PASS |
| CD4 Top (Distillate) | HD exhaust | 98.87% | 99.32% | ✅ PASS |
| CD4 Bottom | D₂ product | 97.77% | 95.73% | ✅ PASS |

### Acceptance Criteria Status

| Criterion | Status | Evidence |
|-----------|--------|----------|
| ISS-I 4-column cascade converges | ✅ PASS | 18 iterations, residual 4.98×10⁻⁶ |
| Global Mass Balance Conservation | ✅ PASS | Error < 0.01% (Total feed 102.677 mol/h = Total products) |
| CD2 top D₂ purity > 99.9% | ✅ PASS | 99.99% |
| CD3 bottom T₂ purity > 90% | ✅ PASS | 95.55% |
| CD4 top HD concentration > 95% | ✅ PASS | 98.87% |
| CD4 bottom D₂ product > 90% | ✅ PASS | 97.77% |
| Temperatures within ±2.0 K | ✅ PASS | Max deviation 0.38 K |
