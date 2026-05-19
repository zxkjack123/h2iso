# h2iso

**Hydrogen Isotope Thermodynamics** — Cryogenic VLE properties and distillation solver for H₂/HD/HT/D₂/DT/T₂ systems.

## Features

- **VLE Property Engine** (`h2iso.vle`): Souers vapor pressure correlations (DIPPR 101), quantum corrections, binary interaction parameters, bubble/dew point calculations, K-values, isothermal flash.
- **MESH Distillation Solver** (`h2iso.mesh`): CasADi-based steady-state column solver supporting 15–100 theoretical stages with continuation warm-start strategy.
- **Profile Export** (`h2iso.mesh.export`): CSV, JSON, and MAT output formats for integration with MATLAB/Simulink or Modelica workflows.
- **Modelica Initialization** (`h2iso.codegen`): Generate `.mos` scripts for OpenModelica dynamic model initialization.

## Installation

```bash
pip install h2iso
```

For solver functionality (requires CasADi + IPOPT):

```bash
pip install h2iso[solver]
```

## Quick Links

- [Quick Start](quickstart.md) — Solve your first column in 5 minutes
- [VLE API Reference](api/vle.md) — Vapor pressure, K-values, flash
- [MESH API Reference](api/mesh.md) — Column solver, continuation, export
- [Validation Report](validation/mesh_report.md) — Wang 2022 benchmark results

## Species

h2iso handles the six homonuclear and heteronuclear hydrogen isotopologues:

| Index | Species | Name |
|-------|---------|------|
| 0 | H₂ | Protium |
| 1 | HD | Hydrogen-Deuteride |
| 2 | HT | Hydrogen-Tritide |
| 3 | D₂ | Deuterium |
| 4 | DT | Deuterium-Tritide |
| 5 | T₂ | Tritium |

Compositions are always 6-element arrays in this order.
