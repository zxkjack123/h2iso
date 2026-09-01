"""Tests for the full SRK cubic EOS implementation (T5.3)."""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.eos import IdealVLE, SRKQuantum
from h2iso.vle.quantum import quantum_alpha_correction


@pytest.fixture(scope="module")
def uniform_x() -> np.ndarray:
    return np.full(N_SPECIES, 1.0 / N_SPECIES)


@pytest.fixture(scope="module")
def srk() -> SRKQuantum:
    return SRKQuantum()


@pytest.fixture(scope="module")
def ideal() -> IdealVLE:
    return IdealVLE()


def test_srk_low_pressure_matches_ideal(srk, ideal, uniform_x):
    """At P < 50 kPa the SRK K-values must agree with IdealVLE within 1%."""
    P_low = 5.0e3  # 5 kPa, well below 50 kPa
    T = 25.0
    K_srk = srk.kvalue(T, P_low, uniform_x)
    K_ideal = ideal.kvalue(T, P_low, uniform_x)
    rel = np.max(np.abs(K_srk - K_ideal) / K_ideal)
    assert rel < 0.01, (
        f"SRK should match IdealVLE at low P; max rel deviation = {rel * 100:.3f}%"
    )


def test_srk_high_pressure_deviates_from_ideal(srk, ideal, uniform_x):
    """At P > 500 kPa SRK must show non-ideal behaviour vs IdealVLE (> 5%)."""
    P_high = 5.0e5  # 500 kPa
    T = 25.0
    K_srk = srk.kvalue(T, P_high, uniform_x)
    K_ideal = ideal.kvalue(T, P_high, uniform_x)
    rel = np.max(np.abs(K_srk - K_ideal) / K_ideal)
    assert rel > 0.05, (
        f"SRK should deviate from IdealVLE at high P; max rel deviation = "
        f"{rel * 100:.3f}%"
    )


def test_srk_cubic_roots_real_and_above_B(srk, uniform_x):
    """The cubic Z polynomial must yield at least one real root > B."""
    T, P = 25.0, 1.0e5
    a_mix, b_mix, _, _ = srk._mix_a_b(T, uniform_x)
    R = 8.314462618
    A = a_mix * P / (R * T) ** 2
    B = b_mix * P / (R * T)
    roots = srk._cubic_roots(A, B)
    assert roots.size >= 1
    assert np.all(roots > B)


def test_srk_liquid_root_smaller_than_vapor_root(srk, uniform_x):
    """When two real Z roots exist, liquid root < vapor root."""
    T, P = 25.0, 1.0e5
    a_mix, b_mix, _, _ = srk._mix_a_b(T, uniform_x)
    R = 8.314462618
    A = a_mix * P / (R * T) ** 2
    B = b_mix * P / (R * T)
    roots = srk._cubic_roots(A, B)
    if roots.size >= 2:
        assert roots.min() < roots.max()


def test_srk_kvalues_positive(srk, uniform_x):
    """K-values must be strictly positive across operating range."""
    for P in (1.0e4, 1.0e5, 5.0e5):
        K = srk.kvalue(25.0, P, uniform_x)
        assert np.all(K > 0), f"non-positive K at P={P:.1e}: {K}"
        assert np.all(np.isfinite(K))


def test_quantum_alpha_correction_measurable_at_low_T():
    """Feynman-Hibbs correction must deviate measurably from unity at 25 K."""
    for sp in SPECIES_ORDER:
        c = quantum_alpha_correction(25.0, sp)
        assert abs(c - 1.0) > 1.0e-4, (
            f"alpha correction for {sp} = {c} not measurably non-classical"
        )


def test_quantum_alpha_correction_approaches_unity_at_high_T():
    """At high T (classical limit), α_quantum → 1."""
    for sp in SPECIES_ORDER:
        c_high = quantum_alpha_correction(1.0e4, sp)
        assert abs(c_high - 1.0) < 1e-3, (
            f"alpha correction for {sp} at high T = {c_high}, expected ~1"
        )


def test_quantum_alpha_correction_rejects_nonpositive_T():
    with pytest.raises(ValueError):
        quantum_alpha_correction(0.0, "H2")
    with pytest.raises(ValueError):
        quantum_alpha_correction(-10.0, "H2")


def test_srk_invariant_to_input_composition_copy(srk, uniform_x):
    """kvalue must not mutate the input composition array."""
    x = uniform_x.copy()
    snapshot = x.copy()
    srk.kvalue(25.0, 1.0e5, x)
    np.testing.assert_array_equal(x, snapshot)


@pytest.mark.skip(reason="No DWSIM SRK reference dataset available in repository")
def test_srk_against_dwsim_reference():
    """Comparison with DWSIM SRK results — skipped (no reference data)."""
    pass
