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

pytest.importorskip("casadi")

from h2iso.mesh.column import Column, ColumnSpec


def _mass_balance_ok(balance: float, z_i: float, F: float) -> bool:
    """Per-component mass-balance acceptance criterion.

    A component closes if ``|balance| <= max(atol, rtol * F * z_i)``, where
    ``rtol = 1e-4`` is the original relative tolerance and ``atol = 1e-5 * F``
    is an absolute floor.  The floor covers both feed-absent components
    (``z_i == 0``) and ppm/ppb-level *non-zero* feeds, for which the purely
    relative term would fall below IPOPT's ``tol=1e-8``.  The original
    ``max(z_i, 1e-10)`` relative floor demanded an absolute closure of ~1e-14,
    which caused spurious failures once ``ipopt.bound_relax_factor`` was
    disabled.

    The discriminating power of this criterion (a genuine ``1e-3 * F`` loss is
    rejected) is asserted by
    :meth:`TestColumnSolve.test_mass_balance_criterion_detects_real_loss` and
    :meth:`TestColumnSolve.test_mass_balance_criterion_covers_trace_feeds`.
    """
    atol = 1e-5 * F
    rtol = 1e-4 * F * z_i
    return abs(balance) <= max(atol, rtol)


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
            z_i = spec.feed_composition[i]
            assert _mass_balance_ok(balance, z_i, F), (
                f"Component {i} mass balance failed: balance={balance:.3e}, "
                f"z_i={z_i:.3e}, F={F:.3e}"
            )

    def test_mass_balance_criterion_detects_real_loss(self, cd2_column_spec):
        """Non-masking proof for the feed-absent absolute-tolerance criterion.

        The real converged solution satisfies ``_mass_balance_ok`` for every
        feed-absent component, while a genuine ``1e-3 * F`` loss injected into
        that component is rejected.  This proves the criterion is not vacuous
        and cannot hide a real mass-balance violation.
        """
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        spec = cd2_column_spec
        F = spec.feed_flow
        D = spec.distillate_to_feed * F
        B = F - D
        x_D = result.x_profile[0]
        x_B = result.x_profile[-1]

        absent = [i for i in range(6) if spec.feed_composition[i] == 0.0]
        assert absent, "fixture must have at least one feed-absent component"

        for i in absent:
            balance = D * x_D[i] + B * x_B[i] - F * spec.feed_composition[i]
            # The real solution is inside the absolute tolerance ...
            assert _mass_balance_ok(balance, 0.0, F), (
                f"real feed-absent balance {abs(balance):.3e} rejected"
            )
            # ... and a genuine 1e-3*F loss MUST be rejected (anti-masking).
            loss = balance - 1e-3 * F
            assert not _mass_balance_ok(loss, 0.0, F), (
                f"criterion failed to reject a 1e-3*F loss on component {i}: "
                f"{abs(loss):.3e} accepted"
            )

    def test_mass_balance_criterion_covers_trace_feeds(self):
        """Trace-but-nonzero feeds must not demand sub-tolerance closure.

        Real fixtures (e.g. ISS-O) carry ppm/ppb-level *non-zero* feed
        compositions.  A purely relative criterion would demand closure below
        IPOPT's ``tol`` for those components; the unified
        ``max(atol, rtol*F*z_i)`` floor must cover them while still rejecting a
        genuine loss (PM4012 P1).
        """
        F = 100.0
        residual = 1e-9  # typical solver numerical floor for a trace component
        z_trace = 1e-9  # ppm-level, non-zero feed
        assert _mass_balance_ok(residual, z_trace, F), (
            f"trace feed z={z_trace:.1e} with residual {residual:.1e} was rejected"
        )
        # The unified criterion must still reject a real loss on that component.
        assert not _mass_balance_ok(1e-3 * F, z_trace, F)

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
                f"T not monotone: T[{j}]={T[j]:.4f} > T[{j + 1}]={T[j + 1]:.4f}"
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
            ColumnSpec(
                n_stages=1,
                feed_stage=1,
                feed_flow=100.0,
                feed_composition=self._valid_feed(),
                pressure=101325.0,
                reflux_ratio=3.0,
                distillate_to_feed=0.5,
            )

    def test_distillate_to_feed_above_one_rejected(self):
        with pytest.raises(ValueError, match="distillate_to_feed"):
            ColumnSpec(
                n_stages=10,
                feed_stage=5,
                feed_flow=100.0,
                feed_composition=self._valid_feed(),
                pressure=101325.0,
                reflux_ratio=3.0,
                distillate_to_feed=1.5,
            )

    def test_distillate_to_feed_zero_rejected(self):
        with pytest.raises(ValueError, match="distillate_to_feed"):
            ColumnSpec(
                n_stages=10,
                feed_stage=5,
                feed_flow=100.0,
                feed_composition=self._valid_feed(),
                pressure=101325.0,
                reflux_ratio=3.0,
                distillate_to_feed=0.0,
            )


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


class TestColumnBoundRelaxation:
    """PM4012 T2: disable IPOPT bound relaxation so profiles stay non-negative.

    IPOPT's default ``bound_relax_factor`` (1e-8) is numerically equal to the
    ``Stream`` non-negativity tolerance, so the solver could return
    compositions inside ``(-1e-8, 0)`` that the ``Stream`` constructor rejects.
    ``Column.build_nlp`` pins ``ipopt.bound_relax_factor = 0.0``; these tests
    lock that option in and verify the resulting profiles are ``>= 0.0``.

    RED on stock IPOPT options; GREEN once the option is set.
    """

    def test_build_nlp_disables_bound_relaxation(self, cd2_column_spec, monkeypatch):
        """Production NLP options must contain ipopt.bound_relax_factor == 0.0."""
        import casadi

        captured: dict = {}
        real_nlpsol = casadi.nlpsol

        def spy(name, plugin, nlp, opts):
            captured["opts"] = dict(opts)
            return real_nlpsol(name, plugin, nlp, opts)

        monkeypatch.setattr(casadi, "nlpsol", spy)
        Column(cd2_column_spec).build_nlp()

        opts = captured.get("opts", {})
        assert opts.get("ipopt.bound_relax_factor") == 0.0, (
            f"bound_relax_factor not disabled: opts={opts}"
        )

    def test_small_column_profiles_nonnegative(self, cd2_column_spec):
        """15-stage CD2 solve must yield non-negative x/y profiles."""
        col = Column(cd2_column_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            pytest.skip("Solver did not converge")

        x_min = float(result.x_profile.min())
        y_min = float(result.y_profile.min())
        assert x_min >= 0.0, f"x_profile min={x_min:.3e} < 0.0"
        assert y_min >= 0.0, f"y_profile min={y_min:.3e} < 0.0"
