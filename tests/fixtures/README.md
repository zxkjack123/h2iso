# Wang 2022 Benchmark Fixtures

## Source

- **Authors**: X. Wang et al.
- **Title**: "Hydrogen isotope inventory evaluation of hydrogen isotopes separation system of CFETR using Aspen Plus simulator"
- **Journal**: Fusion Engineering and Design, Volume 184, 2022
- **DOI**: 10.1016/j.fusengdes.2022.113078

## Files

| File | Content |
|------|---------|
| `wang2022_issi_cd2.json` | ISS-I CD2 column specification (75 stages, NBI feed) |
| `wang2022_issi_cd2_results.json` | DWSIM calculation results for ISS-I CD2 |
| `wang2022_issi.json` | ISS-I full 4-column (CD1+CD2+CD3+CD4+E1+E2) specification |
| `wang2022_issi_results.json` | Calculation results and Aspen comparison for full ISS-I |
| `wang2022_isso.json` | ISS-O 3-column (CD1+CD2+CD3) specification |
| `wang2022_isso_results.json` | DWSIM calculation results for ISS-O |

## Data Provenance

- Column specifications extracted from Tables 1, 5, 8, 9 of Wang et al. 2022
- DWSIM results from automated benchmark runs on DWSIM 9.0.5 (headless .NET 8)
- Originally created in `tricys` repo branch `feature/dwsim-equivalence-verification`
- Migrated to h2iso on 2026-05-19

## Usage

These fixtures serve as reference data for validating:
1. VLE calculations (K-values, bubble/dew points at column conditions)
2. MESH solver steady-state results (composition profiles, temperatures, heat loads)
