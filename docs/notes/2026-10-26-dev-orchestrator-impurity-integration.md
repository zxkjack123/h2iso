---
note_id: "2026-10-26-dev-orchestrator-impurity-integration"
date: "2026-10-26"
author_agent: "dev-orchestrator"
pr_ref: "TBD"  # to be replaced by the pull-request number when the request is opened
change_scope:
  - ".gitignore"
  - "docs/api/impurities.md"
  - "docs/validation/issi_report.md"
  - "docs/validation/isso_report.md"
  - "docs/validation/vle_report.md"
  - "mkdocs.yml"
  - "script/demo_cd2_impurity.py"
  - "script/demo_cd2_purge.py"
  - "script/demo_iss_impurity.py"
  - "src/h2iso/cli.py"
  - "src/h2iso/codegen/modelica_init.py"
  - "src/h2iso/codegen/modelica_records.py"
  - "src/h2iso/data/parameters/hetp_reference.json"
  - "src/h2iso/data/parameters/impurity_data.json"
  - "src/h2iso/equilibrator/exchange.py"
  - "src/h2iso/flowsheet/schema.py"
  - "src/h2iso/flowsheet/sweep.py"
  - "src/h2iso/impurities.py"
  - "src/h2iso/impurity_routing.py"
  - "src/h2iso/mesh/__init__.py"
  - "src/h2iso/mesh/column.py"
  - "src/h2iso/mesh/efficiency.py"
  - "src/h2iso/mesh/enthalpy.py"
  - "src/h2iso/mesh/export.py"
  - "src/h2iso/mesh/geometry.py"
  - "src/h2iso/mesh/holdup.py"
  - "src/h2iso/mesh/performance.py"
  - "src/h2iso/parity/cases.py"
  - "src/h2iso/parity/report.py"
  - "src/h2iso/purge.py"
  - "src/h2iso/species.py"
  - "src/h2iso/vle/mixing.py"
  - "src/h2iso/vle/quantum.py"
  - "src/h2iso/vle/souers.py"
  - "tests/benchmark/test_performance.py"
  - "tests/e2e/test_modelica_init_override.py"
  - "tests/fixtures/README.md"
  - "tests/fixtures/wang2022/wang2022_issi.json"
  - "tests/fixtures/wang2022/wang2022_issi_cd2.json"
  - "tests/fixtures/wang2022/wang2022_issi_cd2_impurity.json"
  - "tests/fixtures/wang2022/wang2022_isso.json"
  - "tests/test_codegen/test_modelica_init_optional.py"
  - "tests/test_data_resources.py"
  - "tests/test_flowsheet/test_cli_flowsheet.py"
  - "tests/test_flowsheet/test_impurity_routing.py"
  - "tests/test_flowsheet/test_purge.py"
  - "tests/test_flowsheet/test_schema.py"
  - "tests/test_flowsheet/test_sweep.py"
  - "tests/test_mesh/test_efficiency.py"
  - "tests/test_mesh/test_export.py"
  - "tests/test_mesh/test_holdup.py"
  - "tests/test_mesh/test_holdup_packed.py"
  - "tests/test_mesh/test_impurity_column.py"
  - "tests/test_mesh/test_iss_i_aspen_validation.py"
  - "tests/test_mesh/test_performance.py"
  - "tests/test_mesh/test_wang2022_mesh.py"
  - "tests/test_vle/test_impurity.py"
  - "tests/test_vle/test_wang2022_vle.py"
kind: "process"
status: "frozen"
---

# Impurity-cascade integration — public integration note

This note accompanies the staged integration of condensable-impurity handling
into `h2iso`. It is aimed at reviewers and maintainers who have no access to any
internal material: it states the public scope, the open risks, and the commands
needed to reproduce the checks. The note itself adds no code and changes no
behaviour.

## Scope

### Purpose of the staged integration

The cryogenic distillation stack (`vle` → `mesh` → `flowsheet` → `codegen`) was
extended so that condensable impurities are carried alongside the six
hydrogen-isotope species. Because the capability touches several layers, the work
was ported as a sequence of small, self-contained increments rather than as one
large change: each increment is its own commit, so a reviewer can follow the
engineering one layer at a time and the history stays bisectable.

The increments, in order, cover:

* an impurity registry plus property data, and an extended `flash` path
  (`src/h2iso/impurities.py`, `src/h2iso/data/parameters/impurity_data.json`,
  `src/h2iso/vle/mixing.py`);
* column-geometry import and an HETP → theoretical-stage conversion layer
  (`src/h2iso/mesh/geometry.py`);
* stage efficiency, holdup correlations, and their integration into the column
  model (`src/h2iso/mesh/efficiency.py`, `src/h2iso/mesh/holdup.py`,
  `src/h2iso/mesh/column.py`);
* an optional Modelica initial-value export channel and an `-overrideFile`
  mechanism (`src/h2iso/codegen/modelica_init.py`,
  `src/h2iso/codegen/modelica_records.py`);
* impurity cascade routing, a condenser purge branch, and the matching CLI and
  API surface (`src/h2iso/impurity_routing.py`, `src/h2iso/purge.py`,
  `src/h2iso/flowsheet/`, `src/h2iso/cli.py`);
* fixtures, tests, demonstration scripts, and API documentation.

### Public file surface

The `change_scope` list in the front matter enumerates every path this delivery
touches. The paths span `src/h2iso/**`, `tests/**`, `docs/**`, `script/**`,
`.gitignore`, and `mkdocs.yml`. No path outside that list belongs to the
delivery.

### Release history

The published branch is rebuilt from the current tip of `asipp/main` (`179ec7a`)
instead of being pushed from the working branch. The ten audit commits will be
folded into nine release commits; the fold is intended to leave the published
tree matching the audited tree byte for byte. The original local audit line of
history is retained locally only and is never pushed.

## Risks

### Experimental capability

The impurity handling is an **experimental** port. It is wired into the normal
code paths and covered by tests, but it has **not** been physically validated: no
experimental measurement was used to confirm the impurity behaviour, and no
result produced with this capability should be quoted as a validated physical
result. Treat it as a reviewable engineering increment, not as a validated
predictive tool.

### Open decisions — PENDING-D1 … D6

Six questions remain open and are deliberately not defaulted:

* **D1** — routing convention for non-condensable versus frozen components:
  whether the delivered revision's convention is adopted.
* **D2** — implementation route: whether core-group decomposition plus an
  impurity post-processing / tracer layer replaces a literal full-component
  walk.
* **D3** — degraded-validation convention for the packing correlations where no
  public worked case exists.
* **D4** — whether the cross-repository long-duration run is replaced by an
  OpenModelica equivalence check.
* **D5** — definition of the dilution bandwidth (relative change versus a bound
  set by the feed impurity fraction).
* **D6** — whether the cross-repository long-duration environment can be run at
  all.

### Long-duration cross-repository run not validated

The cross-repository long-duration simulation (1000 s, in `tricys`) has **not**
been run. The Modelica-side checks in this repository are not equivalent to that
run, and no claim of equivalence is made.

### Aspen baseline not re-validated

The Aspen-side cases (TC1–TC5) were not re-validated: the Aspen baseline files
are unchanged, and no new Aspen cases were added. The existing Aspen baseline
must not be mixed with the impurity extension.

### End-to-end toolchain version

The end-to-end Modelica tests were run on **OpenModelica 1.27.0**. The original
author used **1.26.3**. The two versions have not been shown to be equivalent, so
the end-to-end result carries that version caveat.

### Release-history provenance

Some of the early working commits referred to internal documents in their file
text and in their commit messages. Those references are not part of the published
branch: the release line is rebuilt from `179ec7a` (see *Release history*), and
every blob of every commit on that line, plus every commit message, is scanned
for such references before anything is pushed. The original audit line stays
local and is kept for traceability. This note deliberately repeats no internal
reference.

## Reproduction

Every command below runs in a CI-aligned environment; a developer-local virtual
environment is not a valid source of evidence.

### Environment

```bash
# Python 3.11 with the CI dependency set
python3.11 -m venv /tmp/h2iso-ci
/tmp/h2iso-ci/bin/python -m pip install --upgrade pip
/tmp/h2iso-ci/bin/python -m pip install -c constraints/py3.11.txt -e ".[dev,solver]"
```

Python 3.9 is supported as well: use `python3.9` together with
`constraints/py3.9.txt`. The matrix in `.github/workflows/ci.yml` pins the exact
versions for 3.9, 3.11, and 3.12.

### Checks

```bash
# Import smoke — confirms which tree is under test
/tmp/h2iso-ci/bin/python -c "import h2iso; print(h2iso.__file__)"

# Lint and formatting
/tmp/h2iso-ci/bin/ruff check src/ tests/
/tmp/h2iso-ci/bin/ruff format --check src/ tests/

# Default regression; e2e and benchmark are excluded by the addopts in pyproject.toml
/tmp/h2iso-ci/bin/python -m pytest tests/ -q

# End-to-end Modelica export — needs `omc` on PATH (the run cited here used OpenModelica 1.27.0)
/tmp/h2iso-ci/bin/python -m pytest tests/e2e -q --override-ini="addopts=--benchmark-disable"

# Performance benchmark — excluded by addopts, so run it explicitly
/tmp/h2iso-ci/bin/python -m pytest tests/benchmark --benchmark-enable --override-ini="addopts=" -q

# Packaging
/tmp/h2iso-ci/bin/python -m pip wheel . --no-deps -w /tmp/h2iso-wheel
```

### Reference systems

The regression fixtures under `tests/fixtures/wang2022/` are public reference
systems (the ISS-I and ISS-O distillations and the CD2 column). They are the
anchors the tests rely on. The impurity fixture is an extension of the CD2
fixture and is not part of the Aspen baseline.
