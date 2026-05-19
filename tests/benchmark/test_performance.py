"""Performance regression benchmarks (T6.3).

Establishes performance baselines for key h2iso operations.  Uses
``pytest-benchmark`` so CI can detect significant regressions (> 50% slowdown).

Baseline numbers are documented in ``docs/validation/performance_baseline.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from h2iso.flowsheet.schema import load_flowsheet
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.mesh.column import ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver
from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.mixing import bubble_pressure

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wang2022"


@pytest.fixture(scope="module")
def cd2_spec() -> ColumnSpec:
    with open(FIXTURES / "wang2022_issi_cd2.json") as f:
        ref = json.load(f)

    feed = np.zeros(N_SPECIES)
    comp = ref["feed"]["composition_mole_fraction"]
    for i, sp in enumerate(SPECIES_ORDER):
        feed[i] = comp.get(sp, 0.0)

    col_data = ref["column"]
    return ColumnSpec(
        n_stages=15,
        feed_stage=8,
        feed_flow=ref["feed"]["total_flow_mol_h"],
        feed_composition=feed,
        pressure=col_data["pressure_top_Pa"],
        reflux_ratio=col_data["reflux_ratio"],
        distillate_to_feed=col_data["distillate_to_feed_ratio"],
    )


@pytest.mark.benchmark(group="mesh")
def test_benchmark_cd2_75_plate(benchmark, cd2_spec):
    """CD2 75-plate solve baseline (~10s on dev workstation)."""

    def _solve():
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=75, n_substeps=3)
        result = solver.solve(cd2_spec)
        assert result.final.convergence_info["success"]
        return result

    benchmark.pedantic(_solve, rounds=2, iterations=1, warmup_rounds=0)


@pytest.mark.benchmark(group="flowsheet")
def test_benchmark_isso_three_column(benchmark):
    """ISS-O three-column solve baseline (~30s on dev workstation)."""
    fixture = FIXTURES / "wang2022_isso.json"

    def _solve():
        config = load_flowsheet(fixture)
        solver = SequentialModularSolver(
            config, method="wegstein", continuation_substeps=3
        )
        result = solver.solve(max_iter=50, tol=1e-4)
        assert result.converged
        return result

    benchmark.pedantic(_solve, rounds=2, iterations=1, warmup_rounds=0)


@pytest.mark.benchmark(group="vle")
def test_benchmark_bubble_pressure_1000x(benchmark):
    """1000 bubble-pressure evaluations baseline (< 1s)."""
    rng = np.random.default_rng(42)
    samples = []
    for _ in range(1000):
        x = rng.uniform(0.05, 1.0, size=N_SPECIES)
        x /= x.sum()
        T = float(rng.uniform(20.0, 30.0))
        samples.append((T, x))

    def _run():
        total = 0.0
        for T, x in samples:
            P, _y = bubble_pressure(T, x)
            total += P
        return total

    benchmark.pedantic(_run, rounds=3, iterations=1, warmup_rounds=1)
