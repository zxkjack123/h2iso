"""Task 4.2 error-path regression tests for VLE and enthalpy numerical safety."""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.mesh.enthalpy import liquid_enthalpy_numeric
from h2iso.species import N_SPECIES
from h2iso.vle.mixing import kvalue, rachford_rice


class TestKvalueRejectsNonPositive:
    """kvalue must surface degenerate EOS outputs instead of silently returning K<=0."""

    def test_zero_kvalue_raises(self):
        class ZeroEOS:
            def kvalue(self, T, P, x):
                return np.zeros(N_SPECIES)

        x = np.ones(N_SPECIES) / N_SPECIES
        with pytest.raises(ValueError, match="K-values"):
            kvalue(25.0, 101325.0, x=x, eos=ZeroEOS())

    def test_negative_kvalue_raises(self):
        class BadEOS:
            def kvalue(self, T, P, x):
                K = np.ones(N_SPECIES)
                K[0] = -0.1
                return K

        x = np.ones(N_SPECIES) / N_SPECIES
        with pytest.raises(ValueError, match="K-values"):
            kvalue(25.0, 101325.0, x=x, eos=BadEOS())


class TestRachfordRiceNoSilentFallback:
    """Rachford-Rice must compute a real V (not the legacy 0.5 fallback)."""

    def test_legacy_silent_fallback_case_now_resolves(self):
        # Real K profile previously hit the silent `return 0.5` fallback because
        # of an inverted V-bound calculation. Now it must return a meaningful V
        # in (0, 1) — explicitly NOT 0.5 — and the residual must vanish.
        z = np.array([0.0, 0.0, 0.0, 0.25, 0.5, 0.25])
        K = np.array([2.9456, 1.8515, 1.5037, 1.2350, 1.0055, 0.8252])
        V = rachford_rice(z, K)
        assert 0.0 < V < 1.0
        assert abs(V - 0.5) > 1e-3, "V must not be the legacy 0.5 fallback value"
        residual = float(np.sum(z * (K - 1) / (1 + V * (K - 1))))
        assert abs(residual) < 1e-8

    def test_mixed_kvalues_returns_correct_root(self):
        # Symmetric case: z=[0.5,0.5,...], K=[2, 0.5,...] -> V=0.5 by symmetry.
        z = np.array([0.5, 0.5, 0.0, 0.0, 0.0, 0.0])
        K = np.array([2.0, 0.5, 1.0, 1.0, 1.0, 1.0])
        V = rachford_rice(z, K)
        assert abs(V - 0.5) < 1e-6


class TestEnthalpyRejectsNonPositiveT:
    """liquid_enthalpy_numeric must raise when T <= 0 (log domain)."""

    def test_zero_temperature_raises(self):
        x = np.zeros(N_SPECIES)
        x[0] = 1.0
        with pytest.raises(ValueError, match="T > 0"):
            liquid_enthalpy_numeric(0.0, x)

    def test_negative_temperature_raises(self):
        x = np.zeros(N_SPECIES)
        x[0] = 1.0
        with pytest.raises(ValueError, match="T > 0"):
            liquid_enthalpy_numeric(-1.0, x)
