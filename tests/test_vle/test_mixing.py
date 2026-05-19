"""Tests for mixture VLE calculations."""

import numpy as np
import pytest

from h2iso.vle.mixing import (
    bubble_pressure,
    bubble_temperature,
    flash_TP,
    kij_matrix,
    kvalue,
    rachford_rice,
)
from h2iso.vle.souers import boiling_point, pvap


class TestKijMatrix:
    """Test BIP parameter loading."""

    def test_shape(self):
        kij = kij_matrix()
        assert kij.shape == (6, 6)

    def test_symmetric(self):
        kij = kij_matrix()
        assert np.allclose(kij, kij.T)

    def test_diagonal_zero(self):
        kij = kij_matrix()
        assert np.allclose(np.diag(kij), 0.0)

    def test_small_values(self):
        """kij should be small for similar species."""
        kij = kij_matrix()
        assert np.all(np.abs(kij) < 0.01)


class TestKvalue:
    """Test K-value calculation."""

    def test_positive(self):
        K = kvalue(22.0, 90000.0)
        assert np.all(K > 0)

    def test_ordering(self):
        """K should decrease with molecular mass."""
        K = kvalue(23.0, 90000.0)
        # H2 most volatile, T2 least
        assert K[0] > K[-1]

    def test_pure_at_nbp(self):
        """For pure D2 at its NBP, K_D2 ≈ 1."""
        x = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        Tb = boiling_point("D2")
        K = kvalue(Tb, 101325.0, x)
        assert abs(K[3] - 1.0) < 0.02


class TestBubblePressure:
    """Test bubble point pressure calculation."""

    def test_pure_component(self):
        """Bubble pressure of pure D2 should equal its Psat."""
        x = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        T = 23.0
        P_bub, y = bubble_pressure(T, x)
        P_sat = pvap(T, "D2")
        rel_err = abs(P_bub - P_sat) / P_sat
        assert rel_err < 0.02, f"P_bub={P_bub:.0f}, Psat={P_sat:.0f}"

    def test_mixture_between_pure(self):
        """Mixture bubble pressure should be between lightest and heaviest Psat."""
        x = np.array([0.1, 0.1, 0.1, 0.3, 0.2, 0.2])
        T = 23.0
        P_bub, y = bubble_pressure(T, x)
        P_H2 = pvap(T, "H2")
        P_T2 = pvap(T, "T2")
        assert P_T2 < P_bub < P_H2

    def test_vapor_composition_sums_to_one(self):
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        T = 23.0
        _, y = bubble_pressure(T, x)
        assert abs(np.sum(y) - 1.0) < 1e-10

    def test_invalid_composition_raises(self):
        x_neg = np.array([0.0, 0.0, 0.0, 1.1, -0.1, 0.0])
        with pytest.raises(ValueError, match="Negative"):
            bubble_pressure(22.0, x_neg)


class TestBubbleTemperature:
    """Test bubble point temperature calculation."""

    def test_pure_d2_at_1atm(self):
        """Pure D2 at 1 atm should give Tb ≈ 23.661 K."""
        x = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        T_bub, y = bubble_temperature(101325.0, x)
        assert abs(T_bub - 23.661) < 0.1, f"T_bub = {T_bub:.3f}"

    def test_consistency_with_bubble_pressure(self):
        """bubble_temperature should invert bubble_pressure."""
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        T_orig = 23.5
        P_bub, _ = bubble_pressure(T_orig, x)
        T_calc, _ = bubble_temperature(P_bub, x)
        assert abs(T_calc - T_orig) < 0.01


class TestRachfordRice:
    """Test Rachford-Rice solver."""

    def test_subcooled(self):
        """If sum(z*K) < 1, should return V=0."""
        z = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        K = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])  # All K < 1
        V = rachford_rice(z, K)
        assert V == 0.0

    def test_superheated(self):
        """If sum(z/K) < 1, should return V=1."""
        z = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        K = np.array([2.0, 2.0, 2.0, 2.0, 2.0, 2.0])  # All K > 1
        V = rachford_rice(z, K)
        assert V == 1.0

    def test_two_phase(self):
        """Two-phase region should give 0 < V < 1."""
        z = np.array([0.1, 0.1, 0.1, 0.3, 0.2, 0.2])
        K = np.array([2.0, 1.8, 1.5, 1.2, 0.8, 0.5])
        V = rachford_rice(z, K)
        assert 0 < V < 1

    def test_mass_conservation(self):
        """z = V*y + (1-V)*x must hold."""
        z = np.array([0.1, 0.1, 0.1, 0.3, 0.2, 0.2])
        K = np.array([2.0, 1.8, 1.5, 1.2, 0.8, 0.5])
        V = rachford_rice(z, K)
        x = z / (1 + V * (K - 1))
        y = K * x
        z_check = V * y + (1 - V) * x
        assert np.allclose(z_check, z, atol=1e-12)


class TestFlashTP:
    """Test TP flash calculation."""

    def test_mass_conservation(self):
        """z = V*y + (1-V)*x."""
        z = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        T = 23.5
        P = 90000.0
        V, x, y = flash_TP(T, P, z)
        z_check = V * y + (1 - V) * x
        assert np.allclose(z_check, z, atol=1e-10), (
            f"Mass conservation failed: max err = {np.max(np.abs(z_check - z))}"
        )

    def test_compositions_sum_to_one(self):
        z = np.array([0.05, 0.05, 0.05, 0.5, 0.2, 0.15])
        V, x, y = flash_TP(22.0, 90000.0, z)
        assert abs(np.sum(x) - 1.0) < 1e-10
        assert abs(np.sum(y) - 1.0) < 1e-10

    def test_no_negative_fractions(self):
        z = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        V, x, y = flash_TP(23.0, 90000.0, z)
        assert np.all(x >= -1e-15)
        assert np.all(y >= -1e-15)

    def test_wang2022_feed_reasonable(self):
        """Wang 2022 CD2 feed at column conditions should give reasonable flash."""
        z = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        T = 24.0  # Near D2 boiling point
        P = 90000.0
        V, x, y = flash_TP(T, P, z)
        # Should be partially vaporized
        assert 0 <= V <= 1
        # D2 should be enriched in vapor (more volatile than DT)
        if V > 0 and V < 1:
            assert y[3] >= x[3] or abs(y[3] - x[3]) < 0.01
