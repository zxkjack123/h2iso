"""Tests for tray holdup correlations (holdup/efficiency extension, declared fixture).

Worked examples reproduced (both from published, cross-checked sources):

* Bennett-Agrawal: Perry's Chemical Engineers' Handbook, 7th ed., Sec. 14,
  Example 11 "Pressure Drop, Sieve Plate" (Method B).  Published value
  h_L = 23.23 mm; tolerance below is 2% (the SI-form weir coefficient is
  slightly rounded relative to the mm-form used in the example).
* Hofhuis-Zuiderweg: Zarzycki & Chacuk, *Absorption: Fundamentals and
  Applications*, Example 12-A.  Published value h_cL = 0.0268 m.

Packed-column correlations are covered in a separate test class added with
the Stichlmair / Bravo-Fair / Rocha-Bravo-Fair implementations.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("casadi")  # h2iso.mesh imports the CasADi solver package

from h2iso.mesh.geometry import ColumnGeometry
from h2iso.mesh.holdup import (
    clear_liquid_height_bennett_agrawal,
    clear_liquid_height_hofhuis_zuiderweg,
    liquid_holdup_tray_bennett_agrawal,
    liquid_holdup_tray_hofhuis_zuiderweg,
    tray_active_area,
    tray_weir_length,
    vapor_holdup_tray,
)


class TestBennettAgrawalWorkedExample:
    """Perry 7th ed. Sec. 14, Example 11 (Method B), reproduced."""

    # Example inputs
    SIGMA_MN_M = 25.0
    RHO_L = 841.0
    RHO_V = 0.481
    D_HOLE_MM = 5.0
    F_VA = 2.32  # m/s * sqrt(kg/m3), based on active area
    H_W_MM = 38.0
    Q_PER_WEIR = 0.00727  # m^3/s (per unit weir length, see report note)

    def _calculate(self):
        u_a = self.F_VA / math.sqrt(self.RHO_V)
        return clear_liquid_height_bennett_agrawal(
            u_active=u_a,
            q_liquid_per_weir=self.Q_PER_WEIR,
            h_w=self.H_W_MM / 1000.0,
            rho_l=self.RHO_L,
            rho_v=self.RHO_V,
        )

    def test_k_s(self):
        _, info = self._calculate()
        assert info["K_s"] == pytest.approx(0.080, rel=1e-3)

    def test_phi_e(self):
        _, info = self._calculate()
        assert info["phi_e"] == pytest.approx(0.284, rel=2e-2)

    def test_clear_liquid_height(self):
        h_l, _ = self._calculate()
        assert h_l == pytest.approx(0.02323, rel=2e-2)  # 23.23 mm published

    def test_units_are_metres(self):
        h_l, _ = self._calculate()
        assert 0.01 < h_l < 0.05


class TestBennettAgrawalGeometry:
    def _geometry(self) -> ColumnGeometry:
        return ColumnGeometry(
            column_type="tray",
            diameter_m=0.6,
            tray_count=40,
            tray_spacing_m=0.3,
            tray_type="sieve",
            weir_height_m=0.05,
        )

    def test_holdup_volume_consistent(self):
        geom = self._geometry()
        hyd = liquid_holdup_tray_bennett_agrawal(
            geom,
            q_liquid_m3_s=1.0e-4,
            q_vapor_m3_s=0.05,
            rho_l=70.0,
            rho_v=2.5,
        )
        assert hyd.liquid_volume_m3 == pytest.approx(
            hyd.active_area_m2 * hyd.h_clear_liquid_m
        )
        assert hyd.froth_height_m == pytest.approx(hyd.h_clear_liquid_m / hyd.phi_e)
        assert hyd.liquid_volume_m3 > 0

    def test_density_inversion_raises(self):
        with pytest.raises(ValueError, match="density"):
            clear_liquid_height_bennett_agrawal(
                u_active=1.0,
                q_liquid_per_weir=1e-4,
                h_w=0.05,
                rho_l=1.0,
                rho_v=2.0,
            )

    def test_phi_floor_warns_in_cryo_like_conditions(self):
        # small density difference -> K_s large -> phi_e below the floor
        with pytest.warns(UserWarning, match="phi_e"):
            h_l, info = clear_liquid_height_bennett_agrawal(
                u_active=5.0,
                q_liquid_per_weir=1e-4,
                h_w=0.05,
                rho_l=71.0,
                rho_v=69.0,
            )
        assert info["phi_e"] == pytest.approx(0.05)
        assert h_l > 0


class TestHofhuisZuiderwegWorkedExample:
    """Zarzycki & Chacuk, *Absorption*, Example 12-A, reproduced."""

    def test_clear_liquid_height(self):
        psi = 0.0154 / 0.54  # FP / b
        h_cl = clear_liquid_height_hofhuis_zuiderweg(psi=psi, h_w=0.1, hole_pitch=0.014)
        assert h_cl == pytest.approx(0.0268, rel=1e-2)

    def test_dhulesia_variant(self):
        psi = 0.0154 / 0.54
        h_orig = clear_liquid_height_hofhuis_zuiderweg(
            psi=psi, h_w=0.1, hole_pitch=0.014, mode="original"
        )
        h_dhu = clear_liquid_height_hofhuis_zuiderweg(
            psi=psi, h_w=0.1, hole_pitch=0.014, mode="dhulesia_froth"
        )
        assert h_orig > 0 and h_dhu > 0
        assert h_dhu != pytest.approx(h_orig)

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            clear_liquid_height_hofhuis_zuiderweg(
                psi=0.01, h_w=0.05, hole_pitch=0.014, mode="bogus"
            )

    def test_weir_range_warning(self):
        with pytest.warns(UserWarning, match="validity"):
            clear_liquid_height_hofhuis_zuiderweg(psi=0.01, h_w=0.15, hole_pitch=0.014)


class TestHofhuisZuiderwegGeometry:
    def test_geometry_wrapper(self):
        geom = ColumnGeometry(
            column_type="tray",
            diameter_m=2.0,
            tray_count=20,
            tray_spacing_m=0.6,
            tray_type="sieve",
            weir_height_m=0.08,
            weir_length_m=1.4,
            hole_pitch_m=0.014,
            hole_diameter_m=0.005,
        )
        hyd = liquid_holdup_tray_hofhuis_zuiderweg(
            geom,
            q_liquid_m3_s=4.0e-3,
            q_vapor_m3_s=1.0,
            rho_l=800.0,
            rho_v=1.2,
        )
        assert hyd.liquid_volume_m3 > 0
        assert hyd.active_area_m2 == pytest.approx(tray_active_area(geom))
        assert "psi" in hyd.extras

    def test_missing_pitch_raises(self):
        geom = ColumnGeometry(
            column_type="tray",
            diameter_m=2.0,
            tray_count=20,
            tray_spacing_m=0.6,
            weir_height_m=0.08,
        )
        with pytest.raises(ValueError, match="hole_pitch"):
            liquid_holdup_tray_hofhuis_zuiderweg(
                geom,
                q_liquid_m3_s=4.0e-3,
                q_vapor_m3_s=1.0,
                rho_l=800.0,
                rho_v=1.2,
            )


class TestTrayHelpersAndVapor:
    def test_default_weir_length(self):
        geom = ColumnGeometry(column_type="tray", diameter_m=0.6, weir_height_m=0.05)
        assert tray_weir_length(geom) == pytest.approx(0.7 * 0.6)

    def test_explicit_weir_length(self):
        geom = ColumnGeometry(
            column_type="tray", diameter_m=0.6, weir_length_m=0.5, weir_height_m=0.05
        )
        assert tray_weir_length(geom) == 0.5

    def test_active_area_default_downcomer(self):
        geom = ColumnGeometry(column_type="tray", diameter_m=0.6, weir_height_m=0.05)
        a_t = geom.cross_section_area_m2
        assert tray_active_area(geom) == pytest.approx(a_t * 0.8)

    def test_vapor_holdup(self):
        geom = ColumnGeometry(
            column_type="tray",
            diameter_m=0.6,
            tray_count=10,
            tray_spacing_m=0.3,
            weir_height_m=0.05,
        )
        active = tray_active_area(geom)
        v_v = vapor_holdup_tray(geom, h_froth_m=0.1)
        assert v_v == pytest.approx(active * (0.3 - 0.1))

    def test_vapor_holdup_flooding_warns(self):
        geom = ColumnGeometry(
            column_type="tray",
            diameter_m=0.6,
            tray_count=10,
            tray_spacing_m=0.3,
            weir_height_m=0.05,
        )
        with pytest.warns(UserWarning, match="flooding"):
            assert vapor_holdup_tray(geom, h_froth_m=0.4) == pytest.approx(0.0)
