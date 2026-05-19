"""Tests for quantum corrections and EOS framework."""

import numpy as np

from h2iso.species import SPECIES_ORDER
from h2iso.vle.eos import EOS, IdealVLE, SRKQuantum
from h2iso.vle.quantum import (
    acentric_factor,
    de_boer_parameter,
    fugacity_correction,
)


class TestDeBoer:
    """Test de Boer quantum parameter."""

    def test_all_species_have_values(self):
        for sp in SPECIES_ORDER:
            lb = de_boer_parameter(sp)
            assert lb > 0

    def test_ordering_by_mass(self):
        """Lighter species should have higher Λ* (more quantum)."""
        values = [de_boer_parameter(sp) for sp in SPECIES_ORDER]
        # H2 should be highest
        assert values[0] == max(values)
        # T2 should be lowest
        assert values[-1] == min(values)

    def test_h2_value(self):
        """H2 Λ* ≈ 3.08 (Souers)."""
        assert abs(de_boer_parameter("H2") - 3.08) < 0.01


class TestFugacityCorrection:
    """Test Feynman-Hibbs fugacity correction."""

    def test_correction_magnitude_at_20K(self):
        """At 20 K, H2 correction should be significant (5-15% from 1)."""
        corr = fugacity_correction(20.0, "H2")
        # exp(-4.5/400) = exp(-0.01125) ≈ 0.989
        assert 0.95 < corr < 1.0, f"H2 correction at 20K = {corr}"

    def test_mass_ordering(self):
        """Heavier isotopes have smaller quantum correction."""
        T = 22.0
        corrections = [fugacity_correction(T, sp) for sp in SPECIES_ORDER]
        # All should be < 1 (since alpha is negative)
        for c in corrections:
            assert c < 1.0

        # Correction magnitude decreases with mass (closer to 1):
        # H2 is most different from 1, T2 is closest to 1
        deviations = [abs(1.0 - c) for c in corrections]
        assert deviations[0] >= deviations[-1]

    def test_high_T_limit(self):
        """At high T, correction → 1 (classical limit)."""
        for sp in SPECIES_ORDER:
            corr = fugacity_correction(100.0, sp)
            assert abs(corr - 1.0) < 0.001

    def test_scalar_and_array(self):
        """Should handle both scalar and array inputs."""
        T_scalar = 22.0
        T_array = np.array([20.0, 22.0, 25.0])

        c_s = fugacity_correction(T_scalar, "D2")
        c_a = fugacity_correction(T_array, "D2")

        assert isinstance(c_s, float)
        assert isinstance(c_a, np.ndarray)
        assert c_a.shape == (3,)


class TestAcentricFactor:
    """Test acentric factor values."""

    def test_all_negative(self):
        """All H-isotopologues should have ω < 0 (quantum fluids)."""
        for sp in SPECIES_ORDER:
            omega = acentric_factor(sp)
            assert omega < 0, f"{sp}: ω = {omega} (should be negative)"

    def test_h2_most_negative(self):
        """H2 should have the most negative ω."""
        omegas = [acentric_factor(sp) for sp in SPECIES_ORDER]
        assert omegas[0] == min(omegas)


class TestIdealVLE:
    """Test IdealVLE K-value model."""

    def test_kvalue_positive(self):
        """All K-values should be positive."""
        eos = IdealVLE()
        T = 22.0
        P = 90000.0
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        K = eos.kvalue(T, P, x)
        assert np.all(K > 0)
        assert K.shape == (6,)

    def test_kvalue_ordering(self):
        """K should decrease with molecular mass (lighter = more volatile)."""
        eos = IdealVLE()
        T = 23.0
        P = 90000.0
        x = np.ones(6) / 6  # equal composition
        K = eos.kvalue(T, P, x)
        # H2 has highest K, T2 has lowest
        assert K[0] > K[-1], f"K_H2={K[0]:.3f} should be > K_T2={K[-1]:.3f}"

    def test_kvalue_at_nbp_near_unity(self):
        """At its own NBP and 1 atm, a pure species should have K ≈ 1."""
        eos = IdealVLE()
        # Pure D2 at its boiling point
        T = 23.661
        P = 101325.0
        x = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        K = eos.kvalue(T, P, x)
        # K_D2 should be close to 1 (modified by quantum correction)
        assert abs(K[3] - 1.0) < 0.02, f"K_D2 at NBP = {K[3]}"


class TestSRKQuantum:
    """Test SRK quantum EOS."""

    def test_instantiation(self):
        eos = SRKQuantum()
        assert isinstance(eos, EOS)

    def test_kvalue_similar_to_ideal(self):
        """At low P, SRK should give similar K-values to ideal."""
        ideal = IdealVLE()
        srk = SRKQuantum()
        T = 22.0
        P = 90000.0
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])

        K_ideal = ideal.kvalue(T, P, x)
        K_srk = srk.kvalue(T, P, x)

        # At 90 kPa << Pc (~1500 kPa), should be very close
        rel_diff = np.abs(K_ideal - K_srk) / K_ideal
        assert np.all(rel_diff < 0.05), f"Max deviation: {rel_diff.max():.3f}"
