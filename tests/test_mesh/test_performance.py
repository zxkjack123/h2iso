"""Tests for hardware geometry -> equivalent theoretical stages (conversion layer).

Covers:
1. HETP-mode conversion for packed columns (with/without end stages, ceiling)
2. Tray-efficiency-mode conversion
3. Validation and error paths (missing inputs, invalid geometry, bad efficiency)
4. HETP reference database lookup mechanics
5. ColumnGeometry construction from the flowsheet schema
"""

from __future__ import annotations

import pytest

pytest.importorskip("casadi")  # h2iso.mesh imports the CasADi solver package

from h2iso.flowsheet.schema import ColumnConfig
from h2iso.mesh.geometry import ColumnGeometry
from h2iso.mesh.performance import (
    ColumnPerformance,
    equivalent_hetp,
    load_hetp_database,
    lookup_hetp,
    resolve_theoretical_stages,
)


class TestPackedHETP:
    def test_basic_conversion_with_end_stages(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.75, hetp_m=0.05
        )
        perf = ColumnPerformance(mode="hetp")
        # 3.75 / 0.05 = 75 contact stages + condenser + reboiler
        assert resolve_theoretical_stages(geom, perf) == 77

    def test_basic_conversion_without_end_stages(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.75, hetp_m=0.05
        )
        perf = ColumnPerformance(mode="hetp")
        assert resolve_theoretical_stages(geom, perf, include_end_stages=False) == 75

    def test_ceiling_rounding(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.61, hetp_m=0.05
        )
        perf = ColumnPerformance(mode="hetp")
        # 72.2 -> 73 contact stages (+2)
        assert resolve_theoretical_stages(geom, perf) == 75

    def test_hetp_precedence_performance_over_geometry(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.75, hetp_m=0.10
        )
        perf = ColumnPerformance(mode="hetp", hetp_m=0.05)
        assert resolve_theoretical_stages(geom, perf) == 77

    def test_hetp_falls_back_to_geometry(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.0, hetp_m=0.06
        )
        perf = ColumnPerformance(mode="hetp")
        # 3.0 / 0.06 = 50 + 2
        assert resolve_theoretical_stages(geom, perf) == 52

    def test_effective_height_override(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.75, hetp_m=0.05
        )
        perf = ColumnPerformance(mode="hetp", effective_height_m=2.5)
        # 2.5 / 0.05 = 50 + 2
        assert resolve_theoretical_stages(geom, perf) == 52

    def test_missing_hetp_raises(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_height_m=3.75
        )
        with pytest.raises(ValueError, match="hetp"):
            resolve_theoretical_stages(geom, ColumnPerformance(mode="hetp"))

    def test_missing_height_raises(self):
        geom = ColumnGeometry(column_type="packed", diameter_m=0.06, hetp_m=0.05)
        with pytest.raises(ValueError, match="height"):
            resolve_theoretical_stages(geom, ColumnPerformance(mode="hetp"))


class TestTrayEfficiency:
    def test_basic_conversion(self):
        geom = ColumnGeometry(
            column_type="tray", diameter_m=0.6, tray_count=80, tray_spacing_m=0.3
        )
        perf = ColumnPerformance(mode="tray_efficiency", overall_efficiency=0.8)
        # ceil(0.8*80) = 64 + 2
        assert resolve_theoretical_stages(geom, perf) == 66

    def test_without_end_stages(self):
        geom = ColumnGeometry(
            column_type="tray", diameter_m=0.6, tray_count=80, tray_spacing_m=0.3
        )
        perf = ColumnPerformance(mode="tray_efficiency", overall_efficiency=0.75)
        # ceil(60) = 60
        assert resolve_theoretical_stages(geom, perf, include_end_stages=False) == 60

    def test_missing_tray_count_raises(self):
        geom = ColumnGeometry(column_type="tray", diameter_m=0.6, tray_spacing_m=0.3)
        perf = ColumnPerformance(mode="tray_efficiency", overall_efficiency=0.8)
        with pytest.raises(ValueError, match="tray_count"):
            resolve_theoretical_stages(geom, perf)

    def test_missing_efficiency_raises(self):
        geom = ColumnGeometry(
            column_type="tray", diameter_m=0.6, tray_count=80, tray_spacing_m=0.3
        )
        with pytest.raises(ValueError, match="overall_efficiency"):
            resolve_theoretical_stages(geom, ColumnPerformance(mode="tray_efficiency"))


class TestTheoreticalMode:
    def test_passthrough(self):
        assert (
            resolve_theoretical_stages(None, ColumnPerformance(n_theoretical=75)) == 75
        )

    def test_missing_count_raises(self):
        with pytest.raises(ValueError, match="n_theoretical"):
            resolve_theoretical_stages(None, ColumnPerformance())

    def test_performance_default_none_raises(self):
        with pytest.raises(ValueError):
            resolve_theoretical_stages(None, None)


class TestEquivalentHETP:
    def test_tray_column_equivalent_hetp(self):
        geom = ColumnGeometry(
            column_type="tray", diameter_m=0.6, tray_count=80, tray_spacing_m=0.3
        )
        perf = ColumnPerformance(mode="tray_efficiency", overall_efficiency=0.8)
        # H_active = 24 m; 64 ideal trays -> 0.375 m
        assert equivalent_hetp(geom, perf) == pytest.approx(0.375)

    def test_requires_tray_geometry(self):
        geom = ColumnGeometry(column_type="packed", diameter_m=0.06)
        with pytest.raises(ValueError, match="tray"):
            equivalent_hetp(geom)


class TestPerformanceValidation:
    def test_bad_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            ColumnPerformance(mode="bogus")  # type: ignore[arg-type]

    def test_bad_efficiency_raises(self):
        with pytest.raises(ValueError, match="overall_efficiency"):
            ColumnPerformance(mode="tray_efficiency", overall_efficiency=0.0)
        with pytest.raises(ValueError, match="overall_efficiency"):
            ColumnPerformance(mode="tray_efficiency", overall_efficiency=1.5)

    def test_bad_hetp_raises(self):
        with pytest.raises(ValueError, match="hetp_m"):
            ColumnPerformance(mode="hetp", hetp_m=-0.01)


class TestGeometryValidation:
    def test_bad_void_fraction(self):
        geom = ColumnGeometry(
            column_type="packed", diameter_m=0.06, packing_void_fraction=1.2
        )
        with pytest.raises(ValueError, match="void_fraction"):
            geom.validate()

    def test_bad_diameter(self):
        geom = ColumnGeometry(column_type="theoretical", diameter_m=-0.1)
        with pytest.raises(ValueError, match="diameter"):
            geom.validate()

    def test_packed_holdup_requirements(self):
        geom = ColumnGeometry(column_type="packed", diameter_m=0.06)
        with pytest.raises(ValueError, match="holdup requires"):
            geom.validate(for_holdup=True)

    def test_tray_holdup_requirements(self):
        geom = ColumnGeometry(column_type="tray", diameter_m=0.6)
        with pytest.raises(ValueError, match="holdup requires"):
            geom.validate(for_holdup=True)

    def test_dict_roundtrip(self):
        geom = ColumnGeometry(
            column_type="packed",
            diameter_m=0.06,
            packing_height_m=3.75,
            hetp_m=0.05,
            condenser_volume_m3=1e-3,
        )
        again = ColumnGeometry.from_dict(geom.to_dict())
        assert again == geom

    def test_from_dict_rejects_unknown(self):
        with pytest.raises(ValueError, match="unknown"):
            ColumnGeometry.from_dict({"diameter_m": 0.06, "bogus": 1})

    def test_cross_section_area(self):
        geom = ColumnGeometry(column_type="packed", diameter_m=0.06)
        import math

        assert geom.cross_section_area_m2 == pytest.approx(math.pi * 0.03**2)


class TestHETPDatabase:
    def test_database_parses(self):
        db = load_hetp_database()
        assert "packings" in db and "trays" in db
        assert isinstance(db["packings"], list)

    def test_unknown_packing_returns_none(self):
        assert lookup_hetp("definitely-not-a-packing") is None

    def test_lookup_mechanics_with_test_double(self, monkeypatch):
        import h2iso.mesh.performance as perf

        fake_db = {
            "packings": [
                {
                    "name": "TestPacking",
                    "aliases": ["TP-1"],
                    "hetp_m": 0.05,
                    "source": "unit-test double (not physical data)",
                }
            ],
            "trays": [],
        }
        monkeypatch.setattr(perf, "_HETP_DB", fake_db)
        assert perf.lookup_hetp("testpacking")["hetp_m"] == 0.05
        assert perf.lookup_hetp(" TP-1 ")["hetp_m"] == 0.05
        assert perf.lookup_hetp("other") is None

    def test_resolve_uses_database(self, monkeypatch):
        import h2iso.mesh.performance as perf

        fake_db = {
            "packings": [
                {
                    "name": "TestPacking",
                    "aliases": [],
                    "hetp_m": 0.05,
                    "source": "unit-test double (not physical data)",
                }
            ],
            "trays": [],
        }
        monkeypatch.setattr(perf, "_HETP_DB", fake_db)
        geom = ColumnGeometry(
            column_type="packed",
            diameter_m=0.06,
            packing_height_m=3.0,
            packing_type="TestPacking",
        )
        # 3.0 / 0.05 = 60 + 2
        assert (
            perf.resolve_theoretical_stages(geom, ColumnPerformance(mode="hetp")) == 62
        )

    def test_real_database_populated(self):
        """The shipped database contains literature entries with sources."""
        db = load_hetp_database()
        assert len(db["packings"]) >= 10
        for entry in db["packings"]:
            assert entry["source"], f"{entry['name']} lacks a source"
            if entry["hetp_m"] is not None:
                assert entry["hetp_m"] > 0
        assert len(db["trays"]) >= 2

    def test_real_lookup_b7(self):
        entry = lookup_hetp("B7")
        assert entry is not None
        assert entry["hetp_m"] == pytest.approx(0.065)
        assert "Shere" in entry["source"]

    def test_real_resolve_with_b7_entry(self):
        geom = ColumnGeometry(
            column_type="packed",
            diameter_m=0.06,
            packing_height_m=1.2,
            packing_type="B7",
        )
        # 1.2 / 0.065 = 18.46 -> 19 + 2
        assert resolve_theoretical_stages(geom, ColumnPerformance(mode="hetp")) == 21


class TestFromFlowsheetConfig:
    def test_builds_packed_geometry(self):
        cfg = ColumnConfig(
            name="CD2",
            n_stages=75,
            reflux_ratio=15.0,
            distillate_to_feed=0.979,
            feed_positions={},
            pressure=95000.0,
            inside_diameter_m=0.06,
            HETP_m=0.05,
            condenser_volume_m3=1e-3,
            reboiler_volume_m3=2e-4,
        )
        geom = ColumnGeometry.from_flowsheet_config(cfg)
        assert geom.column_type == "packed"
        assert geom.diameter_m == 0.06
        assert geom.condenser_volume_m3 == 1e-3
        assert geom.reboiler_volume_m3 == 2e-4
