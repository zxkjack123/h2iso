# h2iso Project Snapshot

## Architecture

- **Type**: Pure Python library (src layout)
- **Core Purpose**: Hydrogen isotope (H₂/HD/HT/D₂/DT/T₂) cryogenic VLE properties + CasADi steady-state MESH distillation solver
- **Relationship**: Standalone package consumed by tricys as L1+L2 layer

## Key Modules (planned)

| Module | Purpose |
|--------|---------|
| `src/h2iso/vle/` | L1 — VLE property kernel (Souers, quantum, mixing, flash) |
| `src/h2iso/equilibrator/` | Catalytic isotope exchange equilibrium |
| `src/h2iso/mesh/` | L2 — CasADi MESH column solver |
| `src/h2iso/codegen/` | Modelica initialization file generation |
| `data/parameters/` | JSON parameter database (single source of truth) |

## Tech Stack / Dependencies

- **Core**: numpy, scipy
- **Solver (optional)**: casadi (includes IPOPT)
- **Dev**: pytest, ruff, hypothesis, mkdocs
- **Python**: >= 3.9

## Test Commands

```bash
pytest tests/ -x --tb=short
ruff check src/ tests/
```

## CI

- GitHub Actions (planned): pytest + ruff on push/PR

## Key References

- Souers, P.C. "Hydrogen Properties for Fusion Energy" UCRL-52628 (1986)
- Wang et al. "Hydrogen isotope inventory evaluation..." FED 184 (2022) doi:10.1016/j.fusengdes.2022.113078
- CasADi: Andersson et al. "CasADi: a software framework..." Math Prog Comp (2019)
