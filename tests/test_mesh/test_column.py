"""Tests for N-stage column NLP (Task 2.2).

Tests:
1. 15-stage column converges with IPOPT
2. Mass conservation < 0.01%
3. Temperature profile monotonically increasing top→bottom
4. D2 top purity > 99% (15 stages)
5. Solve time < 10s
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from h2iso.mesh.column import Column, ColumnSpec


@pytest.fixture
def cd2_column_spec() -> ColumnSpec:
    """Wang 2022 CD2 column simplified spec: 15 stages, pure D2/DT/T2 feed."""
    # Feed: D2-rich mixture from tritium extraction
    feed = np.zeros(6)
    feed[3] = 0.90  # D2 (index 3)
    feed[4] = 0.07  # DT (index 4)
    feed[5] = 0.03  # T2 (index 5)
    return ColumnSpec(
        n_stages=15,
        feed_stage=8,
        feed_flow=100.0,  # mol/h
        feed_composition=feed,
        pressure=101325.0,  # 1 atm
        reflux_ratio=5.0,
        distillate_to_feed=0.90,
    )


class TestColumnBuild:
    """Test NLP construction."""

    def test_nlp_builds_without_error(self, cd2_column_spec):
        col = Column(cd2_column_spec)
        nlp_data = col.build_nlp()
        assert "solver" in nlp_data
        assert nlp_data["x0"].shape[0] == 15 * 13  # 15 stages × 13 vars (CMO)

    def test_variable_bounds_shape(self, cd2_column_spec):
        col = Column(cd2_column_spec)
        nlp_data = col.build_nlp()
        n_vars = 15 * 13
        assert nlp_data["lbx"].shape == (n_vars,)
        assert nlp_data["ubx"].shape == (n_vars,)


class TestColumnSolve:
    """Test column solve convergence and physics."""

    def test_ipopt_converges(self, cd2_column_spec):
        """IPOPT should return Solve_Succeeded."""
        col = Column(cd2_column_spec)
        result = col.solve()
        assert result.convergence_info["success"], (
            f"IPOPT failed: {result.convergence_info['status']}"
        )

    def test_mass_conservation(self, cd2_column_spec):
        """Overall mass balance: F = D + B, component balance."""
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        spec = cd2_column_spec
        F = spec.feed_flow
        D = spec.distillate_to_feed * F
        B = F - D

        # Distillate composition = x[0] (condenser), bottoms = x[-1]
        x_D = result.x_profile[0]
        x_B = result.x_profile[-1]

        for i in range(6):
            balance = D * x_D[i] + B * x_B[i] - F * spec.feed_composition[i]
            rel_err = abs(balance) / (F * max(spec.feed_composition[i], 1e-10))
            assert rel_err < 1e-4, f"Component {i} mass balance error = {rel_err:.2e}"

    def test_temperature_monotone(self, cd2_column_spec):
        """Temperature should increase from top (condenser) to bottom (reboiler)."""
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        T = result.T_profile
        # Allow small tolerance for adjacent stages
        for j in range(len(T) - 1):
            assert T[j + 1] >= T[j] - 0.01, (
                f"T not monotone: T[{j}]={T[j]:.4f} > T[{j+1}]={T[j+1]:.4f}"
            )

    def test_d2_purity_top(self, cd2_column_spec):
        """D2 purity in distillate should improve over feed (93%+ for 15 stages).

        Note: α_D2/DT ≈ 1.23, Fenske N_min ≈ 32 for 99%. With only 15 stages,
        thermodynamic limit is ~94-95%. Full 99%+ tested in T2.5 with 75 stages.
        """
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        d2_purity = result.x_profile[0, 3]  # D2 is index 3
        assert d2_purity > 0.93, f"D2 purity = {d2_purity:.4f}, expected > 0.93"
        # Should be higher than feed composition (0.90)
        assert d2_purity > cd2_column_spec.feed_composition[3]

    def test_solve_time(self, cd2_column_spec):
        """15-stage solve should complete in < 10 seconds."""
        col = Column(cd2_column_spec)
        t0 = time.perf_counter()
        col.solve()
        elapsed = time.perf_counter() - t0
        assert elapsed < 10.0, f"Solve took {elapsed:.2f}s, limit 10s"

    def test_compositions_sum_to_one(self, cd2_column_spec):
        """All x and y profiles should sum to 1."""
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        for j in range(cd2_column_spec.n_stages):
            np.testing.assert_allclose(result.x_profile[j].sum(), 1.0, atol=1e-6)
            np.testing.assert_allclose(result.y_profile[j].sum(), 1.0, atol=1e-6)

    def test_flows_positive(self, cd2_column_spec):
        """All flows should be non-negative."""
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        assert np.all(result.L_profile >= -1e-6)
        assert np.all(result.V_profile >= -1e-6)

    def test_heat_duties_sign(self, cd2_column_spec):
        """Condenser duty negative (cooling), reboiler positive (heating)."""
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        assert result.condenser_duty < 0 or abs(result.condenser_duty) < 1e-6
        assert result.reboiler_duty > 0 or abs(result.reboiler_duty) < 1e-6


class TestColumnSpecInputValidation:
    """Task 4.1: ColumnSpec rejects out-of-range parameters at construction."""

    def _valid_feed(self) -> np.ndarray:
        z = np.zeros(6)
        z[3] = 1.0  # pure D2
        return z

    def test_n_stages_below_two_rejected(self):
        with pytest.raises(ValueError, match="n_stages"):
            ColumnSpec(n_stages=1, feed_stage=1, feed_flow=100.0,
                       feed_composition=self._valid_feed(),
                       pressure=101325.0, reflux_ratio=3.0,
                       distillate_to_feed=0.5)

    def test_distillate_to_feed_above_one_rejected(self):
        with pytest.raises(ValueError, match="distillate_to_feed"):
            ColumnSpec(n_stages=10, feed_stage=5, feed_flow=100.0,
                       feed_composition=self._valid_feed(),
                       pressure=101325.0, reflux_ratio=3.0,
                       distillate_to_feed=1.5)

    def test_distillate_to_feed_zero_rejected(self):
        with pytest.raises(ValueError, match="distillate_to_feed"):
            ColumnSpec(n_stages=10, feed_stage=5, feed_flow=100.0,
                       feed_composition=self._valid_feed(),
                       pressure=101325.0, reflux_ratio=3.0,
                       distillate_to_feed=0.0)


class TestEquilibratorUnitValidation:
    """Task 4.1: EquilibratorUnit rejects non-positive temperature."""

    def test_zero_temperature_raises(self):
        from h2iso.flowsheet.stream import Stream
        from h2iso.flowsheet.unit import EquilibratorUnit
        z = np.array([0.4, 0.0, 0.0, 0.4, 0.0, 0.2])
        s = Stream(flow=10.0, composition=z, temperature=25.0, pressure=101325.0)
        unit = EquilibratorUnit(name="EQ", temperature=0.0)
        with pytest.raises(ValueError, match="temperature"):
            unit.solve({"in": s})

    def test_negative_temperature_raises(self):
        from h2iso.flowsheet.stream import Stream
        from h2iso.flowsheet.unit import EquilibratorUnit
        z = np.array([0.4, 0.0, 0.0, 0.4, 0.0, 0.2])
        s = Stream(flow=10.0, composition=z, temperature=25.0, pressure=101325.0)
        unit = EquilibratorUnit(name="EQ", temperature=-5.0)
        with pytest.raises(ValueError, match="temperature"):
            unit.solve({"in": s})
