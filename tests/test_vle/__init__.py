"""Tests for Souers vapor pressure correlations."""

import warnings

import numpy as np
import pytest

from h2iso.species import SPECIES_ORDER
from h2iso.vle.souers import (
    boiling_point,
    critical_point,
    dpvap_dT,
    pvap,
    triple_point,
)


class TestPvapBasic:
    """Basic functionality tests."""

    def test_all_species_callable(self):
        """All 6 species should return a valid pressure."""
        for sp in SPECIES_ORDER:
            Tb = boiling_point(sp)
            P = pvap(Tb, sp)
            assert np.isfinite(P)
            assert P > 0

    def test_invalid_species_raises(self):
        with pytest.raises(ValueError, match="Unknown species"):
            pvap(20.0, "He3")

    def test_scalar_returns_float(self):
        P = pvap(20.0, "H2")
        assert isinstance(P, float)

    def test_array_returns_array(self):
        T = np.array([20.0, 21.0, 22.0])
        P = pvap(T, "H2")
        assert isinstance(P, np.ndarray)
        assert P.shape == (3,)

    def test_monotone_increasing(self):
        """Vapor pressure must increase with temperature."""
        for sp in SPECIES_ORDER:
            Tb = boiling_point(sp)
            T = np.linspace(Tb - 2, Tb + 2, 20)
            P = pvap(T, sp)
            assert np.all(np.diff(P) > 0), f"{sp}: pvap not monotone"


class TestBoilingPoints:
    """Validate against known normal boiling points."""

    # Expected NBP values from Souers (UCRL-52628) and NIST
    EXPECTED_NBP = {
        "H2": 20.271,
        "HD": 22.13,
        "HT": 22.92,
        "D2": 23.661,
        "DT": 24.38,
        "T2": 25.04,
    }

    def test_nbp_at_1atm(self):
        """pvap(Tb) should return ~101325 Pa for each species."""
        for sp, Tb_expected in self.EXPECTED_NBP.items():
            P_at_Tb = pvap(Tb_expected, sp)
            rel_err = abs(P_at_Tb - 101325.0) / 101325.0
            assert rel_err < 0.02, (
                f"{sp}: P(Tb={Tb_expected}K) = {P_at_Tb:.0f} Pa, "
                f"expected ~101325 Pa (rel_err={rel_err:.4f})"
            )

    def test_nbp_ordering(self):
        """Boiling points should increase: H2 < HD < HT < D2 < DT < T2."""
        nbps = [boiling_point(sp) for sp in SPECIES_ORDER]
        for i in range(len(nbps) - 1):
            # HT ≈ D2 (very close), allow equal
            assert nbps[i] <= nbps[i + 1] + 0.01, (
                f"{SPECIES_ORDER[i]} Tb={nbps[i]} >= {SPECIES_ORDER[i+1]} Tb={nbps[i+1]}"
            )


class TestDerivative:
    """Test dPsat/dT."""

    def test_positive_derivative(self):
        """dP/dT should always be positive in liquid range."""
        for sp in SPECIES_ORDER:
            Tb = boiling_point(sp)
            dP = dpvap_dT(Tb, sp)
            assert dP > 0, f"{sp}: dP/dT = {dP} at Tb"

    def test_numerical_consistency(self):
        """Analytical derivative should match finite difference."""
        T = 22.0
        sp = "D2"
        dT = 1e-6
        dP_analytical = dpvap_dT(T, sp)
        dP_numerical = (pvap(T + dT, sp) - pvap(T - dT, sp)) / (2 * dT)
        rel_err = abs(dP_analytical - dP_numerical) / abs(dP_numerical)
        assert rel_err < 1e-5, f"Derivative mismatch: {rel_err:.2e}"


class TestRangeWarning:
    """Test range checking."""

    def test_below_range_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pvap(10.0, "H2")  # Below triple point
            assert len(w) == 1
            assert "outside valid range" in str(w[0].message)

    def test_above_range_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pvap(50.0, "H2")  # Above critical
            assert len(w) == 1
            assert "outside valid range" in str(w[0].message)

    def test_within_range_no_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pvap(20.0, "H2")
            assert len(w) == 0


class TestCriticalTriple:
    """Test critical and triple point accessors."""

    def test_critical_point_values(self):
        Tc, Pc = critical_point("H2")
        assert abs(Tc - 33.145) < 0.01
        assert abs(Pc - 1296400.0) < 100

    def test_triple_point_values(self):
        Ttp, Ptp = triple_point("H2")
        assert abs(Ttp - 13.957) < 0.01
        assert abs(Ptp - 7358.0) < 10

    def test_pvap_at_triple_approx(self):
        """P(Ttp) should approximately equal Ptp."""
        for sp in SPECIES_ORDER:
            Ttp, Ptp = triple_point(sp)
            P_calc = pvap(Ttp, sp)
            rel_err = abs(P_calc - Ptp) / Ptp
            # Allow larger tolerance for estimated species
            assert rel_err < 0.15, (
                f"{sp}: P(Ttp={Ttp}) = {P_calc:.0f}, Ptp = {Ptp:.0f}, "
                f"rel_err = {rel_err:.3f}"
            )
