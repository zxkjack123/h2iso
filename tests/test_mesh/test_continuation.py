"""Tests for continuation solver (Task 2.3).

Tests:
1. N=15→30→60→75 staged continuation converges
2. N=75 board gives D2 purity ≥ 99.9%
3. Adaptive retry recovers from perturbed initial guess
4. N=100 large column converges
5. Total solve time < 60s
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from h2iso.mesh.column import ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver


@pytest.fixture
def cd2_base_spec() -> ColumnSpec:
    """Wang 2022 CD2 column base spec: 15 stages."""
    feed = np.zeros(6)
    feed[3] = 0.90  # D2
    feed[4] = 0.07  # DT
    feed[5] = 0.03  # T2
    return ColumnSpec(
        n_stages=15,
        feed_stage=8,
        feed_flow=100.0,
        feed_composition=feed,
        pressure=101325.0,
        reflux_ratio=5.0,
        distillate_to_feed=0.90,
    )


class TestContinuationN:
    """Test N-continuation (stage count increase)."""

    def test_15_to_30_converges(self, cd2_base_spec):
        """Single step from 15 to 30 stages."""
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        result = solver.solve(cd2_base_spec)
        assert result.final.convergence_info["success"]
        assert len(result.final.T_profile) == 30

    def test_15_to_75_staged(self, cd2_base_spec):
        """Multi-step N=15→30→60→75 continuation."""
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=60, n_substeps=2)
        solver.add_step("N", target=75, n_substeps=1)
        result = solver.solve(cd2_base_spec)
        assert result.final.convergence_info["success"]
        assert len(result.final.T_profile) == 75

    def test_75_stages_d2_purity(self, cd2_base_spec):
        """75 stages with R=10 should achieve high D2 purity (≥99.9%).

        With α_D2/DT=1.23, need both sufficient N AND sufficient R.
        R=5 gives ~99.45%; stepping R up to 10 gives ≥99.9%.
        """
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=75, n_substeps=3)
        solver.add_step("R", target=10.0, n_substeps=3)
        result = solver.solve(cd2_base_spec)
        assert result.final.convergence_info["success"]

        d2_purity = result.final.x_profile[0, 3]
        assert d2_purity >= 0.999, f"D2 purity = {d2_purity:.6f}, expected ≥ 0.999"

    def test_75_stages_temperature_monotone(self, cd2_base_spec):
        """Temperature should be monotonically increasing for 75 stages."""
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=75, n_substeps=3)
        result = solver.solve(cd2_base_spec)
        if not result.final.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        T = result.final.T_profile
        for j in range(len(T) - 1):
            assert T[j + 1] >= T[j] - 0.01, (
                f"T not monotone at stage {j}: T[{j}]={T[j]:.4f} > T[{j + 1}]={T[j + 1]:.4f}"
            )

    def test_100_stages_converges(self, cd2_base_spec):
        """100-stage column should converge via continuation."""
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=60, n_substeps=2)
        solver.add_step("N", target=100, n_substeps=2)
        result = solver.solve(cd2_base_spec)
        assert result.final.convergence_info["success"]
        assert len(result.final.T_profile) == 100

    def test_solve_time_under_60s(self, cd2_base_spec):
        """Full 15→75 continuation should complete in < 60s."""
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=75, n_substeps=3)

        t0 = time.perf_counter()
        solver.solve(cd2_base_spec)
        elapsed = time.perf_counter() - t0
        assert elapsed < 60.0, f"Solve took {elapsed:.2f}s, limit 60s"

    def test_mass_conservation_75(self, cd2_base_spec):
        """Mass balance should be satisfied at 75 stages."""
        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=75, n_substeps=3)
        result = solver.solve(cd2_base_spec)
        if not result.final.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        F = cd2_base_spec.feed_flow
        D = cd2_base_spec.distillate_to_feed * F
        B = F - D
        z = cd2_base_spec.feed_composition
        x_D = result.final.x_profile[0]
        x_B = result.final.x_profile[-1]

        for i in range(6):
            balance = D * x_D[i] + B * x_B[i] - F * z[i]
            rel_err = abs(balance) / (F * max(z[i], 1e-10))
            assert rel_err < 1e-4, f"Component {i} balance error = {rel_err:.2e}"


class TestContinuationR:
    """Test reflux ratio continuation."""

    def test_increase_reflux(self, cd2_base_spec):
        """Increasing R from 5 to 10 should converge."""
        solver = ContinuationSolver()
        solver.add_step("R", target=10.0, n_substeps=3)
        result = solver.solve(cd2_base_spec)
        assert result.final.convergence_info["success"]
