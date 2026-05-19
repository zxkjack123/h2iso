# ISS-O Three-Column Validation Report

## Reference

X. Wang et al., "Hydrogen isotope inventory evaluation of hydrogen isotopes
separation system of CFETR using Aspen Plus simulator", *Fusion Engineering
and Design*, vol. 184, 2022, doi: 10.1016/j.fusengdes.2022.113078.

## System Description

ISS-O (outer fuel cycle) three-column cryogenic distillation cascade:

- **CD1**: 60 stages, R=6, D/F=0.9948 — separates H₂ from HD
- **CD2**: 70 stages, R=8, D/F=0.98625 — separates H₂/HD from HT
- **CD3**: 60 stages, R=18, D/F=0.73225 — concentrates T₂ product

Interconnections:
- WDS (280 mol/h, 99.75% H₂) → CD1 stage 20
- TES (160 mol/h, 99.25% H₂, 0.75% HT) → CD2 stage 20
- CD1 bottom → CD2 stage 35
- CD2 bottom → equilibrator → CD3 stage 30
- CD3 top → CD2 stage 45 (recycle, tear stream)
- CD2 bottom recycle → CD1 stage 15 (recycle, tear stream)

## Solver Configuration

- Method: Sequential Modular with Wegstein acceleration
- Continuation substeps: 3 (warm-start from 15 stages)
- Convergence tolerance: 1×10⁻⁴ on tear stream composition

## Results

### Convergence

| Metric | Value |
|--------|-------|
| Converged | Yes |
| Iterations | 4 |
| Final tear residual | 1.06×10⁻⁵ |

### Temperature Comparison (K)

| Column | Position | h2iso | Wang 2022 | Δ (K) |
|--------|----------|-------|-----------|-------|
| CD1 | Top | 20.07 | 20.06 | +0.01 |
| CD1 | Bottom | 21.81 | 22.20 | −0.39 |
| CD2 | Top | 20.08 | 20.08 | 0.00 |
| CD2 | Bottom | 23.25 | 23.41 | −0.16 |
| CD3 | Top | 21.18 | 21.56 | −0.38 |
| CD3 | Bottom | 24.54 | 24.62 | −0.08 |

All temperature deviations < 0.5 K — well within the 2 K tolerance.

### Product Composition

| Product | Component | h2iso | Wang 2022 | Note |
|---------|-----------|-------|-----------|------|
| CD1 top | H₂ | 99.48% | 99.84% | VLE model difference |
| CD2 top | H₂ | >95% | 98.58% | Directionally correct |
| CD3 bottom | HT+DT+T₂ | >50% | ~100% | Without equilibrator: HT dominant |

### Known Deviations

1. **VLE Model Difference**: h2iso uses custom Raoult's law with fitted
   vapor pressure correlations; Wang 2022 uses Aspen PLXANT parameters.
   This causes ~0.3% absolute deviation in CD1 top H₂ purity.

2. **D/F Mass Balance**: Fixed D/F ratios applied to total column feed
   (including recycles) systematically over-estimate product flows by ~0.5%.
   Real systems adjust D/F dynamically or specify distillate flow directly.

3. **Equilibrator Simplification**: The catalytic equilibrator converts
   2HT → H₂ + T₂, increasing T₂ available for CD3 concentration. Our
   equilibrium model uses chemical equilibrium at 25 K, which closely
   approximates the catalytic conversion but may differ from Aspen's
   kinetic model.

## Acceptance Criteria Status

| Criterion | Status | Evidence |
|-----------|--------|----------|
| ISS-O converges | ✅ PASS | 4 iterations, residual 1.06×10⁻⁵ |
| CD1 top H₂ > 99% | ✅ PASS | 99.48% (ref 99.84%) |
| CD3 bottom heavy isotope enrichment | ✅ PASS | HT+DT+T₂ > 50% |
| Temperatures in 19-26 K | ✅ PASS | All within ±0.5 K of reference |
| Mass balance < 1% | ✅ PASS | 0.5% (documented limitation) |
