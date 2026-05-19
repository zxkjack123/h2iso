"""Tests for isotope exchange equilibrium."""

import numpy as np
import pytest

from h2iso.equilibrator.exchange import (
    atom_fractions,
    equilibrium_composition,
    is_equilibrated,
    keq,
)


class TestKeq:
    """Test equilibrium constant calculation."""

    def test_known_values(self):
        """K1(25K) ≈ 3.82 from Jones 1968."""
        K1 = keq(25.0, "H2_D2_2HD")
        assert 3.5 < K1 < 4.5, f"K1(25K) = {K1}"

    def test_high_T_limit(self):
        """All K should approach 4 at high T (statistical limit)."""
        for rxn in ["H2_D2_2HD", "H2_T2_2HT", "D2_T2_2DT"]:
            K = keq(1000.0, rxn)
            assert abs(K - 4.0) < 0.5, f"{rxn} at 1000K: K = {K}"

    def test_positive(self):
        """K must always be positive."""
        for rxn in ["H2_D2_2HD", "H2_T2_2HT", "D2_T2_2DT"]:
            K = keq(20.0, rxn)
            assert K > 0

    def test_invalid_reaction(self):
        with pytest.raises(ValueError, match="Unknown reaction"):
            keq(25.0, "invalid")


class TestAtomFractions:
    """Test atom fraction calculation."""

    def test_pure_h2(self):
        x = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        H, D, T = atom_fractions(x)
        assert abs(H - 1.0) < 1e-10
        assert abs(D) < 1e-10
        assert abs(T) < 1e-10

    def test_pure_d2(self):
        x = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        H, D, T = atom_fractions(x)
        assert abs(H) < 1e-10
        assert abs(D - 1.0) < 1e-10
        assert abs(T) < 1e-10

    def test_equimolar_hd(self):
        """Pure HD has equal H and D atoms."""
        x = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
        H, D, T = atom_fractions(x)
        assert abs(H - 0.5) < 1e-10
        assert abs(D - 0.5) < 1e-10

    def test_sum_to_one(self):
        x = np.array([0.1, 0.15, 0.05, 0.3, 0.25, 0.15])
        H, D, T = atom_fractions(x)
        assert abs(H + D + T - 1.0) < 1e-10


class TestEquilibriumComposition:
    """Test equilibrium solver."""

    def test_pure_h2(self):
        """Pure protium at equilibrium is just H2."""
        x_eq = equilibrium_composition(1.0, 0.0, 0.0, T=25.0)
        assert abs(x_eq[0] - 1.0) < 1e-6  # All H2

    def test_pure_d2(self):
        """Pure deuterium at equilibrium is just D2."""
        x_eq = equilibrium_composition(0.0, 1.0, 0.0, T=25.0)
        assert abs(x_eq[3] - 1.0) < 1e-6  # All D2

    def test_50_50_HD(self):
        """Equal H and D atoms → mostly HD at equilibrium (K~4)."""
        x_eq = equilibrium_composition(0.5, 0.5, 0.0, T=25.0)
        # With K1 ≈ 4: at equilibrium, HD is dominant
        # For αH=αD=0.5: x_H2 ≈ 0.126, x_HD ≈ 0.504, x_D2 ≈ 0.126
        # (statistical: 0.25, 0.5, 0.25 at K=4 exactly)
        assert x_eq[1] > 0.4, f"HD fraction = {x_eq[1]}"
        assert x_eq[1] > x_eq[0]  # HD > H2
        assert x_eq[1] > x_eq[3]  # HD > D2

    def test_atom_conservation(self):
        """Equilibrium composition must conserve atoms."""
        alpha_H, alpha_D, alpha_T = 0.3, 0.5, 0.2
        x_eq = equilibrium_composition(alpha_H, alpha_D, alpha_T, T=25.0)

        H_out, D_out, T_out = atom_fractions(x_eq)
        assert abs(H_out - alpha_H) < 1e-4
        assert abs(D_out - alpha_D) < 1e-4
        assert abs(T_out - alpha_T) < 1e-4

    def test_equilibrium_satisfied(self):
        """Result must satisfy equilibrium constraints."""
        x_eq = equilibrium_composition(0.3, 0.5, 0.2, T=25.0)
        assert is_equilibrated(x_eq, 25.0, rtol=0.01)

    def test_mole_fractions_valid(self):
        """All fractions non-negative and sum to 1."""
        x_eq = equilibrium_composition(0.4, 0.4, 0.2, T=20.0)
        assert np.all(x_eq >= 0)
        assert abs(np.sum(x_eq) - 1.0) < 1e-10

    def test_fusion_relevant(self):
        """CFEDR relevant: ~50% D, ~50% T, trace H."""
        x_eq = equilibrium_composition(0.01, 0.495, 0.495, T=25.0)
        # Should have significant DT
        assert x_eq[4] > 0.3, f"DT = {x_eq[4]}"
        # Check it's equilibrated
        assert is_equilibrated(x_eq, 25.0, rtol=0.02)


class TestIsEquilibrated:
    """Test equilibrium check function."""

    def test_equilibrium_composition_passes(self):
        x_eq = equilibrium_composition(0.5, 0.5, 0.0, T=25.0)
        assert is_equilibrated(x_eq, 25.0, rtol=0.01)

    def test_non_equilibrium_fails(self):
        """Pure HD is NOT at equilibrium (K1 ≈ 4, not 0)."""
        x_non_eq = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
        # This has Q1 = 1^2/(0*0) → undefined, but atom_fraction is 0.5 H, 0.5 D
        # So it's not equilibrated (because H2 and D2 should be present)
        # Since x_H2=0 and x_D2=0, the check skips these reactions
        # Let's use a clearly non-equilibrium mix
        x_non_eq = np.array([0.5, 0.0, 0.0, 0.5, 0.0, 0.0])
        # Q1 = 0^2/(0.5*0.5) = 0, K1 ≈ 4 → not equilibrated
        assert not is_equilibrated(x_non_eq, 25.0)
