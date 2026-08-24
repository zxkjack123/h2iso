# AGENTS.md — h2iso Project Guide

## Project Overview

h2iso (Hydrogen Isotope Thermodynamics) is an open-source Python package providing
cryogenic VLE (Vapor-Liquid Equilibrium) properties and a steady-state MESH distillation
solver for hydrogen isotope systems (H2/HD/HT/D2/DT/T2). It serves as the L1 (VLE) and
L2 (steady-state MESH) layers of the tricys multi-fidelity distillation framework.

## Project Structure

- `src/h2iso/` — Core package source
  - `species.py` — Six-species definitions (H2, HD, HT, D2, DT, T2)
  - `vle/` — L1 VLE property kernel (Souers vapor pressure, quantum corrections, K-values, BIPs)
  - `mesh/` — L2 CasADi steady-state MESH column solver
  - `equilibrator/` — Catalytic isotope exchange equilibrium (H2+D2<=>2HD etc.)
  - `flowsheet/` — Multi-column flowsheet sequential-modular solver + parameter sweep
  - `codegen/` — Modelica initialization export for tricys dynamic models
  - `data/` — Parameter JSON files (Souers coefficients, BIPs, schemas)
  - `cli.py` — CLI entry point (`h2iso flash/column/flowsheet/sweep/export`)
- `tests/` — Test suite (unit, property-based, benchmark, e2e)
- `docs/` — MkDocs Material documentation
- `.github/` — CI workflows, plans, reviews

## Tech Stack

- **Language**: Python 3.9+ (targets 3.9, tested on 3.9/3.11/3.12)
- **Core deps**: numpy >=1.22, scipy >=1.8
- **Solver**: CasADi >=3.6 (optional, for MESH solver)
- **Dev**: pytest, pytest-cov, pytest-benchmark, ruff, hypothesis
- **Docs**: mkdocs-material, mkdocstrings
- **Integration**: OpenModelica (e2e tests), tricys (L3+ dynamic layer)

## Common Commands

```bash
# Install (editable, with dev + solver deps)
pip install -e ".[dev,solver]"

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Run unit tests (excludes benchmark & e2e by default)
pytest tests/ -x --tb=short

# Run all tests including CasADi solver
pytest tests/ --tb=short

# Run benchmarks only
pytest tests/benchmark/ --benchmark-enable --override-ini="addopts="

# Run e2e tests (requires OpenModelica)
pytest tests/e2e/ -v --override-ini="addopts=--benchmark-disable"

# CLI usage
h2iso flash --T 22.0 --P 90000 --z "D2:0.98,DT:0.02"
h2iso column --config column.json --output results/
h2iso flowsheet --config flowsheet.json --output results/
h2iso sweep --config flowsheet.json --column CD2 --parameter reflux_ratio --start 5 --stop 20 --step 1
h2iso export --input results/profiles.json --format csv

# Build docs
mkdocs serve
```

## Conventions

- Code style: ruff with `target-version = "py39"`, `line-length = 88`
- Lint rules: E, F, W, I (isort), UP (pyupgrade); E501 ignored
- Test markers: `slow` (CasADi solver tests), `benchmark` (performance regression)
- Default pytest excludes `tests/benchmark` and `tests/e2e` via `addopts`
- Source layout: `src/h2iso/` with `setuptools.packages.find` in `pyproject.toml`
- Package data: `data/parameters/*.json`, `data/schemas/*.json`

## Git Remotes

| Remote | URL |
|--------|-----|
| origin | `git@github.com:zxkjack123/h2iso.git` (SSH, primary push) |
| asipp  | `git@github.com:asipp-neutronics/h2iso.git` (upstream org) |

## Related Projects

- **tricys** (`~/opt/tricys`): L3-L5 dynamic distillation framework; h2iso provides L1+L2
- **OpenModelica**: Dynamic simulation engine for e2e integration tests
