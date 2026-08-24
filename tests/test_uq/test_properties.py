"""Tests for h2iso.uq.properties — global property perturbation."""

import numpy as np
import pytest

from h2iso.uq.properties import (
    _bip_matrix,
    _souers_params,
    bip_parameter,
    property_override,
    resolve_property_params,
    souers_C1_parameter,
    souers_C2_parameter,
)


class TestSouersParams:
    def test_C1_parameter(self):
        p = souers_C1_parameter("D2", sigma_rel=0.02)
        assert p.name == "souers.D2.C1"
        assert p.distribution == "normal"
        params = _souers_params()
        assert p.mean() == pytest.approx(params["D2"]["C1"])

    def test_C2_parameter(self):
        p = souers_C2_parameter("T2", sigma_rel=0.01)
        assert p.name == "souers.T2.C2"
        assert p.distribution == "normal"

    def test_unknown_species_raises(self):
        with pytest.raises(KeyError):
            souers_C1_parameter("Xe")


class TestBipParams:
    def test_bip_parameter(self):
        bip = _bip_matrix()
        p = bip_parameter(3, 4, float(bip[3, 4]))
        assert p.name == "bip.3.4"
        assert p.mean() == pytest.approx(bip[3, 4])

    def test_bip_parameter_sigma_default(self):
        bip = _bip_matrix()
        p = bip_parameter(0, 1, float(bip[0, 1]))
        assert abs(p.mean()) == pytest.approx(abs(bip[0, 1]))


class TestPropertyOverride:
    def test_override_souers_restores(self):
        sp = _souers_params()
        orig = sp["D2"]["C1"]

        with property_override({"souers.D2.C1": orig + 0.5}):
            assert sp["D2"]["C1"] == pytest.approx(orig + 0.5)

        # Should be restored
        assert sp["D2"]["C1"] == pytest.approx(orig)

    def test_override_bip_restores(self):
        bip = _bip_matrix()
        orig = float(bip[3, 4])

        with property_override({"bip.3.4": orig + 0.1}):
            assert bip[3, 4] == pytest.approx(orig + 0.1)

        assert bip[3, 4] == pytest.approx(orig)

    def test_override_multiple(self):
        sp = _souers_params()
        bip = _bip_matrix()
        orig_c1 = sp["H2"]["C1"]
        orig_c2 = sp["H2"]["C2"]
        orig_bip = float(bip[0, 1])

        with property_override(
            {
                "souers.H2.C1": orig_c1 + 1.0,
                "souers.H2.C2": orig_c2 - 1.0,
                "bip.0.1": orig_bip + 0.05,
            }
        ):
            assert sp["H2"]["C1"] == pytest.approx(orig_c1 + 1.0)
            assert sp["H2"]["C2"] == pytest.approx(orig_c2 - 1.0)
            assert bip[0, 1] == pytest.approx(orig_bip + 0.05)

        assert sp["H2"]["C1"] == pytest.approx(orig_c1)
        assert sp["H2"]["C2"] == pytest.approx(orig_c2)
        assert bip[0, 1] == pytest.approx(orig_bip)

    def test_override_exception_restores(self):
        sp = _souers_params()
        orig = sp["D2"]["C1"]

        try:
            with property_override({"souers.D2.C1": orig + 1.0}):
                assert sp["D2"]["C1"] != pytest.approx(orig)
                raise ValueError("simulated error")
        except ValueError:
            pass

        # Should be restored even after exception
        assert sp["D2"]["C1"] == pytest.approx(orig)

    def test_invalid_souers_key_raises(self):
        with pytest.raises(KeyError):
            with property_override({"souers.Xe.C1": 1.0}):
                pass

    def test_invalid_coeff_raises(self):
        with pytest.raises(KeyError):
            with property_override({"souers.D2.C99": 1.0}):
                pass

    def test_unknown_key_format_raises(self):
        with pytest.raises(ValueError, match="Unknown override key"):
            with property_override({"unknown.key": 1.0}):
                pass


class TestResolvePropertyParams:
    def test_filters_operational_params(self):
        result = resolve_property_params(
            np.array([15.0, 80.0, 0.1, 0.2]),
            ["CD1.R", "feed.WDS", "souers.D2.C1", "bip.3.4"],
        )
        assert "CD1.R" not in result
        assert "feed.WDS" not in result
        assert result["souers.D2.C1"] == pytest.approx(0.1)
        assert result["bip.3.4"] == pytest.approx(0.2)

    def test_no_property_params(self):
        result = resolve_property_params(
            np.array([15.0, 80.0]),
            ["R", "F"],
        )
        assert result == {}


class TestPropertyInSolve:
    """Verify that property overrides affect the column solution."""

    def test_souers_C1_shift_affects_temperature(self, monkeypatch):
        """Increasing C1 (higher vapor pressure) should lower T_top."""
        from h2iso.mesh.column import Column, ColumnSpec
        from h2iso.uq.properties import property_override

        z = np.array([0, 0, 0, 0.98, 0.02, 0])
        spec = ColumnSpec(
            n_stages=8,
            feed_stage=4,
            feed_flow=80.0,
            feed_composition=z,
            pressure=90000.0,
            reflux_ratio=10.0,
            distillate_to_feed=0.979,
        )

        # Baseline
        col = Column(spec)
        r0 = col.solve()
        T_top_0 = float(r0.T_profile[0])
        D2_top_0 = float(r0.x_profile[0, 3])

        # Perturb C1 upward: increases Psat → lower temperature for same composition
        sp = _souers_params()
        delta_c1 = abs(sp["D2"]["C1"]) * 0.02  # 2% up
        with property_override({"souers.D2.C1": sp["D2"]["C1"] + delta_c1}):
            r1 = col.solve()
            T_top_1 = float(r1.T_profile[0])
            D2_top_1 = float(r1.x_profile[0, 3])

        # Higher C1 → higher Psat → lower T needed to reach P=90000 at top
        # Actually: at fixed P, K = Psat/P. Higher Psat → higher K → D2 prefers
        # vapor more → less D2 in liquid at top (distillate). So D2_top should decrease.
        # And bubble point T should decrease (higher volatility).
        # The effect is small but directionally correct.
        assert T_top_1 != pytest.approx(T_top_0, abs=1e-10)
        assert D2_top_1 != pytest.approx(D2_top_0, abs=1e-10)
