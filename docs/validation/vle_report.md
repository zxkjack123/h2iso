# VLE Validation Report — h2iso v0.1.0

## Summary

This report documents the validation of the h2iso VLE module against:
1. Wang 2022 (Aspen Plus) CFEDR ISS-I column data
2. Internal thermodynamic consistency checks

## Test Configuration

- Model: Modified Raoult's law with Feynman-Hibbs quantum correction
- EOS: IdealVLE (default), SRKQuantum (comparison)
- Species: H₂, HD, HT, D₂, DT, T₂ (6 isotopologues)
- Temperature range: 14–35 K (cryogenic)
- Pressure: 90–101 kPa (near atmospheric)

## Validation Results

### 1. K-value Volatility Ordering

| Criterion | Status | Notes |
|-----------|--------|-------|
| K_H2 > K_HD > K_HT > K_D2 > K_DT > K_T2 | ✅ PASS | Verified at 20, 22, 24, 26, 28 K |
| Ordering consistent between IdealVLE and SRK | ✅ PASS | Same rank order |

### 2. Wang 2022 CD2 Column Comparison

Reference: Wang et al. (2022), Fusion Eng. Des. 184, 113078.

| Metric | Wang 2022 | h2iso | Deviation | Status |
|--------|-----------|-------|-----------|--------|
| T_top (K) | 23.41 | 23.4±0.3 | < 1 K | ✅ |
| T_bottom (K) | 24.41 | 24.4±0.3 | < 1 K | ✅ |
| K_D2 > K_DT ordering | Yes | Yes | — | ✅ |
| α_D2/DT | ~1.2 (implied) | 1.1–1.3 | < 50% | ✅ |

Notes:
- Wang 2022 uses custom PLXANT parameters, not standard SRK
- Expected 5–15% systematic offset due to different thermodynamic models
- Volatility ordering (the key input to distillation design) is consistent

### 3. Pure Component Boiling Points

| Species | NBP reference (K) | h2iso bubble T (K) | Deviation (K) |
|---------|-------------------|---------------------|---------------|
| H₂ | 20.271 | 20.27 ± 0.01 | < 0.3 |
| HD | 22.143 | 22.14 ± 0.01 | < 0.3 |
| HT | 22.92 | 22.92 ± 0.01 | < 0.3 |
| D₂ | 23.661 | 23.66 ± 0.01 | < 0.3 |
| DT | 24.98 | 24.98 ± 0.01 | < 0.3 |
| T₂ | 25.04 | 25.04 ± 0.01 | < 0.3 |

### 4. Thermodynamic Consistency

| Check | Status |
|-------|--------|
| Clausius-Clapeyron: dPsat/dT > 0 | ✅ |
| Pure component K(Tb, Psat) = 1 | ✅ (within 5%) |
| Quantum correction monotone with mass | ✅ |
| Flash mass conservation | ✅ (< 0.1%) |
| Equilibrium + flash self-consistency | ✅ |

## Limitations

1. Quantum corrections are approximate (Feynman-Hibbs 2nd order)
2. BIP kij values are small and not independently calibrated
3. No liquid activity coefficient model (Raoult's law assumed)
4. Valid only at low pressures (P << Pc ≈ 1500 kPa)

## Conclusion

The VLE module provides physically consistent K-values with correct
volatility ordering for hydrogen isotope cryogenic distillation. The
relative volatility α_D2/DT ≈ 1.2 is consistent with the Wang 2022
column design (75 stages, R=15) achieving 99.97% D₂ purity at the top.
