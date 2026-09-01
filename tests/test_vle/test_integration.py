"""VLE integration tests: cross-module consistency checks."""

import numpy as np

from h2iso.equilibrator.exchange import atom_fractions, equilibrium_composition
from h2iso.species import SPECIES_ORDER
from h2iso.vle.eos import IdealVLE, SRKQuantum
from h2iso.vle.mixing import bubble_pressure, bubble_temperature, flash_TP, kvalue
from h2iso.vle.quantum import fugacity_correction
from h2iso.vle.souers import boiling_point, pvap


class TestVLEConsistency:
    """Cross-module VLE consistency checks."""

    def test_bubble_temperature_all_pure(self):
        """Bubble temp for each pure species should match NBP."""
        for i, sp in enumerate(SPECIES_ORDER):
            x = np.zeros(6)
            x[i] = 1.0
            T_bub, _ = bubble_temperature(101325.0, x)
            T_nbp = boiling_point(sp)
            # Within 0.3 K (quantum correction shifts slightly)
            assert abs(T_bub - T_nbp) < 0.3, (
                f"{sp}: T_bubble={T_bub:.3f}, NBP={T_nbp:.3f}"
            )

    def test_flash_at_bubble_gives_V_zero(self):
        """Flash at bubble point should give V ≈ 0."""
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        T = 23.5
        P_bub, _ = bubble_pressure(T, x)
        # Slightly above bubble pressure → subcooled → V=0
        V, x_out, y_out = flash_TP(T, P_bub * 1.01, x)
        assert V == 0.0

    def test_flash_below_bubble_gives_vapor(self):
        """Flash at below bubble pressure should give V > 0."""
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        T = 23.5
        P_bub, _ = bubble_pressure(T, x)
        V, _, _ = flash_TP(T, P_bub * 0.9, x)
        assert V > 0.0

    def test_kvalue_ordering_all_temperatures(self):
        """K-values should maintain volatility order at all temperatures."""
        for T in [20.0, 22.0, 24.0, 26.0, 28.0]:
            K = kvalue(T, 90000.0)
            # H2 most volatile, T2 least (monotone decreasing)
            for i in range(5):
                assert K[i] >= K[i + 1] * 0.95, (
                    f"T={T}: K[{SPECIES_ORDER[i]}]={K[i]:.3f} "
                    f"< K[{SPECIES_ORDER[i + 1]}]={K[i + 1]:.3f}"
                )

    def test_eos_models_agree_trend(self):
        """IdealVLE and SRKQuantum should agree on volatility ordering."""
        ideal = IdealVLE()
        srk = SRKQuantum()
        T = 23.0
        P = 90000.0
        x = np.ones(6) / 6

        K_ideal = ideal.kvalue(T, P, x)
        K_srk = srk.kvalue(T, P, x)

        # Same ordering
        assert np.all(np.argsort(K_ideal)[::-1] == np.argsort(K_srk)[::-1])

    def test_equilibrium_then_flash(self):
        """Equilibrate a D-T mixture, then flash it. Should be self-consistent."""
        # Fusion fuel: 50% D, 50% T atoms
        x_eq = equilibrium_composition(0.0, 0.5, 0.5, T=24.0)

        # Flash at column conditions
        T = 24.0
        P = 90000.0
        V, x_liq, y_vap = flash_TP(T, P, x_eq)

        # Mass conservation (flash normalization introduces ~0.01% rounding)
        z_check = V * y_vap + (1 - V) * x_liq
        assert np.allclose(z_check, x_eq, rtol=1e-3)

        # Atom conservation in each phase
        H_feed, D_feed, T_feed = atom_fractions(x_eq)
        H_liq, D_liq, T_liq = atom_fractions(x_liq)
        H_vap, D_vap, T_vap = atom_fractions(y_vap)

        # D+T should still sum to ~1 (no H present)
        assert abs(D_liq + T_liq - 1.0) < 0.01
        assert abs(D_vap + T_vap - 1.0) < 0.01


class TestVLEThermodynamicConsistency:
    """Thermodynamic consistency tests."""

    def test_gibbs_duhem_direction(self):
        """Gibbs-Duhem: if T increases at constant P, all pvap must increase."""
        P1 = pvap(22.0, "D2")
        P2 = pvap(23.0, "D2")
        assert P2 > P1

    def test_raoults_law_limit(self):
        """At P=Psat for a pure component, that K=1."""
        for i, sp in enumerate(SPECIES_ORDER):
            T = boiling_point(sp)
            P = pvap(T, sp)
            x = np.zeros(6)
            x[i] = 1.0
            K = kvalue(T, P, x)
            # K_i for the pure species should be ~1
            assert abs(K[i] - 1.0) < 0.05, f"{sp}: K={K[i]}"

    def test_quantum_correction_decreases_with_mass(self):
        """Quantum effect on K should decrease with molecular mass."""
        T = 22.0
        corrections = [fugacity_correction(T, sp) for sp in SPECIES_ORDER]
        deviations = [abs(1.0 - c) for c in corrections]
        # Monotone decreasing (lighter = more quantum = more deviation)
        for i in range(5):
            assert deviations[i] >= deviations[i + 1] - 0.001
