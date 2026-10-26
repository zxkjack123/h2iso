"""Packed-column holdup tests (holdup/efficiency extension, 填料塔 part).

Key finding driving the test strategy (cited design note sec. 7): **none of the
packed-column correlations has a published worked example**, so these tests
use independent re-computation of the published formulas (regression locks),
plus dimensional / monotonicity / degradation checks, instead of literature
value comparison.  The two tray correlations keep their literature worked
examples in ``test_holdup.py``.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("casadi")  # h2iso.mesh imports the CasADi solver package

from h2iso.mesh.holdup import (
    liquid_holdup_packed_billet_schultes,
    liquid_holdup_packed_rocha_bravo_fair,
    liquid_holdup_packed_stichlmair,
    vapor_holdup_packed,
)


class TestStichlmairPacked:
    """Stichlmair-Bravo-Fair (1989): h0 = 0.555 Fr_L^(1/3),
    Fr_L = u_L^2 a_p / (g eps^4.65); loading correction with dP."""

    A_P = 250.0  # Mellapak 250Y-like packing
    EPS = 0.95
    RHO_L = 70.0  # liquid hydrogen order of magnitude

    def test_formula_recomputed(self):
        u_l = 0.01
        out = liquid_holdup_packed_stichlmair(u_l, self.A_P, self.EPS)
        fr_l = u_l**2 * self.A_P / (9.81 * self.EPS**4.65)
        h0 = 0.555 * fr_l ** (1.0 / 3.0)
        assert out["Fr_L"] == pytest.approx(fr_l, rel=1e-12)
        assert out["h0"] == pytest.approx(h0, rel=1e-12)
        assert out["h_L"] == pytest.approx(h0, rel=1e-12)

    def test_one_third_power_scaling(self):
        h1 = liquid_holdup_packed_stichlmair(0.01, self.A_P, self.EPS)["h_L"]
        h2 = liquid_holdup_packed_stichlmair(0.08, self.A_P, self.EPS)["h_L"]
        # u_L x8 -> h ~ x8^(2/3) = x4
        assert h2 / h1 == pytest.approx(4.0, rel=1e-9)

    def test_loading_correction(self):
        out = liquid_holdup_packed_stichlmair(
            0.01,
            self.A_P,
            self.EPS,
            dP_irr_per_Z=100.0,
            Z=1.0,
            rho_l=self.RHO_L,
        )
        expected = out["h0"] * (1.0 + 20.0 * (100.0 / (1.0 * self.RHO_L * 9.81)) ** 2)
        assert out["h_L"] == pytest.approx(expected, rel=1e-12)
        assert out["h_L"] > out["h0"]

    def test_load_region_clamp_guard(self):
        # high pressure drop pushes the raw value above the 0.5 guard
        out = liquid_holdup_packed_stichlmair(
            0.01,
            self.A_P,
            self.EPS,
            dP_irr_per_Z=500.0,
            Z=1.0,
            rho_l=self.RHO_L,
        )
        assert out["h_L"] == pytest.approx(0.5)

    def test_zero_flow_degenerates(self):
        out = liquid_holdup_packed_stichlmair(0.0, self.A_P, self.EPS)
        assert out["h_L"] == pytest.approx(0.0)

    def test_viscosity_warning(self):
        with pytest.warns(UserWarning, match="5 mPa"):
            liquid_holdup_packed_stichlmair(0.01, self.A_P, self.EPS, mu_l=8e-3)

    def test_holdup_is_volume_fraction(self):
        for u_l in (1e-4, 1e-3, 1e-2, 0.05):
            out = liquid_holdup_packed_stichlmair(u_l, self.A_P, self.EPS)
            assert 0.0 <= out["h_L"] < self.EPS


class TestBilletSchultesPacked:
    """Billet-Schultes: implemented as the substitute for the (non-existent)
    "Bravo-Fair 1982" holdup correlation; independent re-computation."""

    def _ref(self, u_l, a_p, rho_l, mu_l, c_h):
        g = 9.81
        re_l = u_l * rho_l / (a_p * mu_l)
        fr_l = u_l**2 * a_p / g
        a_h = (
            c_h * re_l**0.15 * fr_l**0.1
            if re_l < 5
            else 0.85 * c_h * re_l**0.25 * fr_l**0.1
        )
        h = (12 * mu_l * a_p**2 * u_l / (rho_l * g)) ** (1 / 3) * a_h ** (2 / 3)
        return re_l, fr_l, h

    def test_both_reynolds_branches(self):
        for u_l in (1e-6, 1e-4, 0.01):
            got = liquid_holdup_packed_billet_schultes(
                u_l, 250.0, 70.0, 1.3e-5, c_h=0.5
            )
            re_l, fr_l, h = self._ref(u_l, 250.0, 70.0, 1.3e-5, 0.5)
            assert got["Re_L"] == pytest.approx(re_l, rel=1e-12)
            assert got["h_L"] == pytest.approx(h, rel=1e-12)

    def test_above_loading_correction(self):
        base = liquid_holdup_packed_billet_schultes(0.01, 250.0, 70.0, 1.3e-5, c_h=0.5)[
            "h_L"
        ]
        at_flood = liquid_holdup_packed_billet_schultes(
            0.01,
            250.0,
            70.0,
            1.3e-5,
            c_h=0.5,
            u_v=0.5,
            u_v_flood=0.5,
            eps=0.95,
        )
        assert at_flood["h_L"] == pytest.approx(at_flood["h_L_flood"], rel=1e-9)
        assert at_flood["h_L_flood"] > base

    def test_invalid_c_h_raises(self):
        with pytest.raises(ValueError, match="c_h"):
            liquid_holdup_packed_billet_schultes(0.01, 250.0, 70.0, 1.3e-5, c_h=0.0)


class TestRochaBravoFair:
    """Rocha-Bravo-Fair (1993).  Independent transcription as a regression
    lock plus the epsilon-convention switch (cited design note sec. 5.3)."""

    # Sulzer DX reference geometry (cited design note table, from the UFRJ thesis)
    B = 0.0064
    H = 0.0029
    THETA = 60.0
    EPS = 0.937
    A_P = 900.0

    RHO_L = 70.0
    RHO_G = 3.0
    MU_L = 1.3e-5
    SIGMA = 0.002  # N/m, liquid hydrogen order of magnitude

    def _call(self, **kw):
        args = dict(
            u_ls=0.002,
            u_gs=0.5,
            rho_l=self.RHO_L,
            rho_g=self.RHO_G,
            mu_l=self.MU_L,
            sigma=self.SIGMA,
            corrugation_base_m=self.B,
            corrugation_height_m=self.H,
            corrugation_angle_deg=self.THETA,
            eps=self.EPS,
            a_p=self.A_P,
        )
        args.update(kw)
        return liquid_holdup_packed_rocha_bravo_fair(**args)

    def test_regression_against_independent_transcription(self):
        out = self._call()
        s = math.sqrt(self.B**2 / 4 + self.H**2)
        sin_t = math.sin(math.radians(self.THETA))
        cos_g = 0.9  # sigma < 0.055 N/m
        u_ls = 0.002
        re_l = u_ls * self.RHO_L * s / self.MU_L
        we_l = u_ls**2 * self.RHO_L * s / self.SIGMA
        fr_l = u_ls**2 / (s * 9.81)
        ft = (29.12 * (we_l * fr_l) ** 0.15 * s**0.359) / (
            re_l**0.2 * self.EPS**0.6 * sin_t**0.3 * (1 - 0.93 * cos_g)
        )
        g_eff = 9.81 * (self.RHO_L - self.RHO_G) / self.RHO_L
        h = (4 * ft / s) ** (2 / 3) * (
            3 * self.MU_L * u_ls / (self.RHO_L * g_eff * sin_t * self.EPS)
        ) ** (1 / 3)
        assert out["S"] == pytest.approx(s, rel=1e-12)
        assert out["Ft"] == pytest.approx(ft, rel=1e-12)
        assert out["h_L"] == pytest.approx(h, rel=1e-12)
        assert out["a_e"] == pytest.approx(ft * 0.35 * self.A_P, rel=1e-12)

    def test_eps_convention_switch(self):
        with_eps = self._call(include_eps_in_denom=True)["h_L"]
        without = self._call(include_eps_in_denom=False)["h_L"]
        # denominator eps*rho*g*sin: including eps increases h_L by eps^(-1/3),
        # equivalently the printed-form value is smaller by eps^(+1/3)
        assert with_eps / without == pytest.approx(self.EPS ** (-1 / 3), rel=1e-9)
        assert without / with_eps == pytest.approx(self.EPS ** (1 / 3), rel=1e-9)

    def test_flooding_raises(self):
        with pytest.raises(ValueError, match="flooding"):
            self._call(dP_per_Z=1025.0, dP_per_Z_flood=1025.0)

    def test_monotonic_in_liquid_velocity(self):
        h1 = self._call(u_ls=0.001)["h_L"]
        h2 = self._call(u_ls=0.004)["h_L"]
        assert h2 > h1

    def test_cos_gamma_branches(self):
        low = self._call(sigma=0.02)
        high = self._call(sigma=0.06)
        assert low["cos_gamma"] == pytest.approx(0.9)
        assert high["cos_gamma"] == pytest.approx(5.211 * 10 ** (-16.835 * 0.06))

    def test_standstill_returns_zero(self):
        out = self._call(u_ls=0.0)
        assert out["h_L"] == pytest.approx(0.0)


class TestPackedVapor:
    def test_vapor_holdup_packed(self):
        v_v = vapor_holdup_packed(eps=0.95, h_l=0.05, area_m2=0.01, height_m=2.0)
        assert v_v == pytest.approx((0.95 - 0.05) * 0.01 * 2.0)

    def test_vapor_holdup_flooding_warns(self):
        with pytest.warns(UserWarning, match="flooding"):
            assert vapor_holdup_packed(
                eps=0.95, h_l=0.96, area_m2=0.01, height_m=2.0
            ) == pytest.approx(0.0)


class TestColumnHoldupIntegration:
    """Column.solve() attaches per-stage holdup when the spec carries a
    geometry; without geometry the profiles stay None (backward compat)."""

    def _solve(self, geometry):
        import numpy as np

        from h2iso.mesh.column import Column, ColumnSpec

        z = np.zeros(6)
        z[3] = 0.98
        z[4] = 0.02
        spec = ColumnSpec(
            n_stages=12,
            feed_stage=6,
            feed_flow=10.0,
            feed_composition=z,
            pressure=95000.0,
            reflux_ratio=15.0,
            distillate_to_feed=0.9,
            geometry=geometry,
        )
        return Column(spec).solve()

    def test_tray_geometry_populates_profiles(self):
        import numpy as np

        from h2iso.mesh.geometry import ColumnGeometry

        geom = ColumnGeometry(
            column_type="tray",
            diameter_m=0.6,
            tray_count=10,
            tray_spacing_m=0.3,
            tray_type="sieve",
            weir_height_m=0.05,
            condenser_volume_m3=1e-3,
            reboiler_volume_m3=2e-4,
        )
        result = self._solve(geom)
        assert result.holdup_l_profile is not None
        assert result.holdup_l_profile.shape == (12,)
        assert np.all(np.isfinite(result.holdup_l_profile))
        assert result.holdup_l_profile[1:-1].min() > 0
        assert result.holdup_l_profile.sum() > 0
        assert result.holdup_v_profile.sum() > 0

    def test_packed_geometry_populates_profiles(self):
        import numpy as np

        from h2iso.mesh.geometry import ColumnGeometry

        geom = ColumnGeometry(
            column_type="packed",
            diameter_m=0.06,
            packing_height_m=0.12,
            packing_type="test",
            packing_specific_area_m2_m3=900.0,
            packing_void_fraction=0.937,
            hetp_m=0.02,
            condenser_volume_m3=1e-3,
            reboiler_volume_m3=2e-4,
        )
        result = self._solve(geom)
        assert result.holdup_l_profile is not None
        assert np.all(np.isfinite(result.holdup_l_profile))
        assert result.holdup_l_profile[1:-1].min() >= 0
        assert result.holdup_l_profile.sum() > 0

    def test_no_geometry_leaves_none(self):
        import numpy as np

        from h2iso.mesh.column import Column, ColumnSpec

        z = np.zeros(6)
        z[3] = 0.98
        z[4] = 0.02
        spec = ColumnSpec(
            n_stages=12,
            feed_stage=6,
            feed_flow=10.0,
            feed_composition=z,
            pressure=95000.0,
            reflux_ratio=15.0,
            distillate_to_feed=0.9,
        )
        result = Column(spec).solve()
        assert result.holdup_l_profile is None
        assert result.holdup_v_profile is None

    def test_packed_geometry_missing_fields_raises(self):
        from h2iso.mesh.geometry import ColumnGeometry

        geom = ColumnGeometry(
            column_type="packed",
            diameter_m=0.06,
            packing_height_m=0.12,
            hetp_m=0.02,
            condenser_volume_m3=1e-3,
            reboiler_volume_m3=2e-4,
        )
        with pytest.raises(ValueError, match="holdup requires"):
            self._solve(geom)


class TestInventoryBridge:
    """An earlier interface decision: keep inventory/ (simple) and holdup.py (detailed) side
    by side, connected by an equivalent-epsilon bridge.  With uniform
    tritium weighting the bridged inventory must reproduce the detailed
    packed-section liquid moles exactly (integral-consistent eps_stage)."""

    PRESSURE = 95000.0

    def _setup(self):
        import numpy as np

        from h2iso.mesh.column import Column, ColumnSpec
        from h2iso.mesh.geometry import ColumnGeometry
        from h2iso.mesh.holdup import evaluate_column_holdup

        z = np.zeros(6)
        z[3] = 0.98
        z[4] = 0.02
        geom = ColumnGeometry(
            column_type="packed",
            diameter_m=0.06,
            packing_height_m=0.12,
            packing_type="test",
            packing_specific_area_m2_m3=900.0,
            packing_void_fraction=0.937,
            hetp_m=0.02,
            condenser_volume_m3=1e-3,
            reboiler_volume_m3=2e-4,
        )
        spec = ColumnSpec(
            n_stages=12,
            feed_stage=6,
            feed_flow=10.0,
            feed_composition=z,
            pressure=self.PRESSURE,
            reflux_ratio=15.0,
            distillate_to_feed=0.9,
            geometry=geom,
        )
        result = Column(spec).solve()
        holdup = evaluate_column_holdup(result, geom, pressure=self.PRESSURE)
        return result, geom, holdup

    def test_bridge_values_positive(self):
        from h2iso.mesh.holdup import bridge_holdup_to_inventory

        _, geom, holdup = self._setup()
        bridge = bridge_holdup_to_inventory(holdup, geom)
        assert bridge["eps_stage"] > 0
        assert bridge["eps_condenser"] > 0
        assert bridge["eps_reboiler"] > 0
        assert bridge["eps_packing"] > 0

    def test_inventory_reproduces_detailed_liquid(self):
        import numpy as np

        from h2iso.inventory.calculator import evaluate_column_inventory
        from h2iso.inventory.models import InventoryGeometry
        from h2iso.mesh.holdup import (
            apply_bridge_to_inventory_geometry,
            bridge_holdup_to_inventory,
        )
        from h2iso.species import SPECIES_ORDER

        result, geom, holdup = self._setup()
        base = InventoryGeometry(
            inside_diameter_m=geom.diameter_m,
            HETP_m=geom.hetp_m,
            condenser_volume_m3=geom.condenser_volume_m3,
            reboiler_volume_m3=geom.reboiler_volume_m3,
        )
        bridge = bridge_holdup_to_inventory(holdup, geom, base=base)
        inv_geom = apply_bridge_to_inventory_geometry(bridge, base)

        # uniform tritium weighting -> inventory liquid = plain liquid moles
        alpha_one = {sp: 1.0 for sp in SPECIES_ORDER}
        inv = evaluate_column_inventory(
            result,
            geometry=inv_geom,
            pressure=self.PRESSURE,
            column_name="test",
            tritium_equivalence=alpha_one,
        )
        detailed_internal = float(np.sum(holdup.liquid_mol_per_stage[1:-1]))
        assert inv.liquid_packed_mol == pytest.approx(detailed_internal, rel=1e-9)

    def test_bridge_rejects_tray_geometry(self):
        from h2iso.mesh.geometry import ColumnGeometry
        from h2iso.mesh.holdup import bridge_holdup_to_inventory

        _, _, holdup = self._setup()
        tray = ColumnGeometry(
            column_type="tray",
            diameter_m=0.6,
            tray_count=10,
            tray_spacing_m=0.3,
            weir_height_m=0.05,
        )
        with pytest.raises(ValueError, match="packed"):
            bridge_holdup_to_inventory(holdup, tray)


class TestBridgeInputGuard:
    """Divisor guards in :func:`bridge_holdup_to_inventory` (F3).

    The bridge divides by the base ``eps_packing`` and by the stage volume
    ``A * HETP``; a degenerate base/geometry used to surface as a bare
    ``ZeroDivisionError``.  These cases drive the bridge directly with
    minimal stand-ins (bypassing the ``InventoryGeometry`` constructor guard)
    so the second line of defence is exercised on its own.
    """

    def _holdup(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            liquid_volume_m3_per_stage=[1e-5, 2e-5, 3e-5, 1e-5],
            liquid_molar_volume_m3_per_mol=[2.5e-5, 2.5e-5, 2.5e-5, 2.5e-5],
        )

    def _base(self, **overrides):
        from types import SimpleNamespace

        fields = dict(
            eps_packing=0.20,
            eps_stage=0.10,
            eps_condenser=0.01,
            eps_reboiler=0.05,
            condenser_volume_m3=1.0e-3,
            reboiler_volume_m3=2.0e-4,
        )
        fields.update(overrides)
        return SimpleNamespace(**fields)

    def _geometry(self, **overrides):
        from h2iso.mesh.geometry import ColumnGeometry

        fields = dict(column_type="packed", diameter_m=0.06, hetp_m=0.02)
        fields.update(overrides)
        return ColumnGeometry(**fields)

    def test_bridge_rejects_zero_eps_packing(self):
        from h2iso.mesh.holdup import bridge_holdup_to_inventory

        with pytest.raises(ValueError, match="eps_packing"):
            bridge_holdup_to_inventory(
                self._holdup(), self._geometry(), base=self._base(eps_packing=0.0)
            )

    def test_bridge_rejects_nonpositive_hetp(self):
        from h2iso.mesh.holdup import bridge_holdup_to_inventory

        for bad in (0.0, -0.02):
            with pytest.raises(ValueError, match="hetp_m"):
                bridge_holdup_to_inventory(
                    self._holdup(), self._geometry(hetp_m=bad), base=self._base()
                )
