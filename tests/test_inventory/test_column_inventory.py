"""Unit tests for column tritium inventory evaluation."""

from __future__ import annotations

import numpy as np
import pytest

# Ensure CasADi is available for ColumnResult import
pytest.importorskip("casadi")

from h2iso.inventory.calculator import evaluate_column_inventory
from h2iso.inventory.models import InventoryGeometry
from h2iso.mesh.column import ColumnResult


@pytest.fixture
def dummy_column_result():
    """Create a dummy 10-stage ColumnResult with pure H2 (zero tritium)."""
    N = 10
    T_prof = np.linspace(20.0, 22.0, N)
    x_prof = np.zeros((N, 6))
    x_prof[:, 0] = 1.0  # 100% H2
    y_prof = x_prof.copy()
    L_prof = np.full(N, 50.0)
    V_prof = np.full(N, 60.0)
    return ColumnResult(
        T_profile=T_prof,
        x_profile=x_prof,
        y_profile=y_prof,
        L_profile=L_prof,
        V_profile=V_prof,
        condenser_duty=-100.0,
        reboiler_duty=100.0,
    )


@pytest.fixture
def dummy_tritium_column_result():
    """Create a dummy 10-stage ColumnResult with 100% T2."""
    N = 10
    T_prof = np.linspace(24.5, 25.5, N)
    x_prof = np.zeros((N, 6))
    x_prof[:, 5] = 1.0  # 100% T2
    y_prof = x_prof.copy()
    L_prof = np.full(N, 50.0)
    V_prof = np.full(N, 60.0)
    return ColumnResult(
        T_profile=T_prof,
        x_profile=x_prof,
        y_profile=y_prof,
        L_profile=L_prof,
        V_profile=V_prof,
        condenser_duty=-100.0,
        reboiler_duty=100.0,
    )


@pytest.mark.slow
class TestColumnInventoryUnit:
    """Test column inventory calculation under controlled boundary conditions."""

    def test_zero_tritium_inventory(self, dummy_column_result):
        """A column with zero tritium species (pure H2) must yield 0.0 inventory."""
        inv = evaluate_column_inventory(dummy_column_result)
        assert inv.total_mol == 0.0
        assert inv.total_grams == 0.0
        assert inv.gas_condenser_mol == 0.0
        assert inv.gas_packed_mol == 0.0
        assert inv.gas_reboiler_mol == 0.0
        assert inv.liquid_condenser_mol == 0.0
        assert inv.liquid_packed_mol == 0.0
        assert inv.liquid_reboiler_mol == 0.0

    def test_pure_t2_inventory_positive(self, dummy_tritium_column_result):
        """A column containing T2 must yield strictly positive inventory."""
        geom = InventoryGeometry(inside_diameter_m=0.06, HETP_m=0.05)
        inv = evaluate_column_inventory(
            dummy_tritium_column_result, geometry=geom, pressure=100000.0
        )
        assert inv.total_mol > 0.0
        assert inv.total_grams > 0.0
        assert inv.total_liquid_mol > inv.total_gas_mol  # Liquid density >> gas density

    def test_geometry_scaling(self, dummy_tritium_column_result):
        """Doubling column diameter should quadruple packed section inventory."""
        geom1 = InventoryGeometry(inside_diameter_m=0.05)
        geom2 = InventoryGeometry(inside_diameter_m=0.10)
        inv1 = evaluate_column_inventory(dummy_tritium_column_result, geometry=geom1)
        inv2 = evaluate_column_inventory(dummy_tritium_column_result, geometry=geom2)

        # Packed section volume scales with D^2
        ratio_packed_gas = inv2.gas_packed_mol / inv1.gas_packed_mol
        ratio_packed_liq = inv2.liquid_packed_mol / inv1.liquid_packed_mol
        assert pytest.approx(ratio_packed_gas, rel=1e-4) == 4.0
        assert pytest.approx(ratio_packed_liq, rel=1e-4) == 4.0

    def test_to_dict_structure(self, dummy_tritium_column_result):
        """to_dict produces proper JSON-serializable structure."""
        inv = evaluate_column_inventory(
            dummy_tritium_column_result, column_name="CD_Test"
        )
        d = inv.to_dict()
        assert d["column_name"] == "CD_Test"
        assert "total_mol" in d
        assert "total_grams" in d
        assert "gas_phase_mol" in d
        assert "liquid_phase_mol" in d


class TestInventoryGeometryInputGuard:
    """Entry guard on ``InventoryGeometry`` (constructor) and the
    ``ColumnGeometry.from_flowsheet_config`` bridge.

    The guard rejects non-physical ``HETP_m`` / ``eps_packing`` at
    construction time so the zero-division / zero-fraction paths cannot be
    entered silently; it is a **pure addition** and leaves every legal
    construction path (defaults included) unchanged.
    """

    def test_defaults_unchanged(self):
        """The historical default construction must keep working (no change)."""
        geom = InventoryGeometry()
        assert geom.HETP_m == 0.05
        assert geom.eps_packing == 0.20

    def test_eps_packing_zero_rejected(self):
        with pytest.raises(ValueError, match="eps_packing"):
            InventoryGeometry(eps_packing=0.0)

    def test_eps_packing_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="eps_packing"):
            InventoryGeometry(eps_packing=1.5)

    def test_hetp_zero_or_negative_rejected(self):
        for bad in (0.0, -1.0):
            with pytest.raises(ValueError, match="HETP_m"):
                InventoryGeometry(HETP_m=bad)

    def test_hetp_nan_rejected(self):
        with pytest.raises(ValueError, match="HETP_m"):
            InventoryGeometry(HETP_m=float("nan"))

    def test_from_flowsheet_config_validates_hetp(self):
        """``from_flowsheet_config`` must run ``validate()`` on the result."""
        from types import SimpleNamespace

        from h2iso.mesh.geometry import ColumnGeometry

        cfg = SimpleNamespace(inside_diameter_m=0.06, HETP_m=-0.01)
        with pytest.raises(ValueError, match="hetp_m"):
            ColumnGeometry.from_flowsheet_config(cfg)
