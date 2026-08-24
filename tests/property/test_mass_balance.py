"""Property-based mass balance invariants for isothermal flash (T6.1)."""

from __future__ import annotations

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from h2iso.species import N_SPECIES
from h2iso.vle.mixing import bubble_pressure, flash_TP

_PROFILE = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


def _compositions():
    return st.lists(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=N_SPECIES,
        max_size=N_SPECIES,
    ).map(lambda v: np.asarray(v, dtype=np.float64) / sum(v))


@_PROFILE
@given(z=_compositions(), T=st.floats(min_value=23.0, max_value=27.0))
def test_flash_TP_overall_mass_balance(z, T):
    """For TP flash: z = (1-V) x + V y must hold component-wise within 1%."""
    # Pick pressure inside the two-phase envelope: use bubble pressure scaled
    P_bub, _ = bubble_pressure(T, z)
    P = 0.6 * P_bub  # ensure some vaporisation
    V, x, y = flash_TP(T, P, z)
    z_back = (1.0 - V) * x + V * y
    rel = np.max(np.abs(z_back - z) / np.maximum(z, 1e-12))
    assert rel < 0.01, f"Mass balance error {rel:.4f} at T={T}, P={P:.3e}, V={V:.3f}"
    assert 0.0 <= V <= 1.0 or abs(V) < 1e-9 or abs(V - 1) < 1e-9


@_PROFILE
@given(z=_compositions(), T=st.floats(min_value=23.0, max_value=27.0))
def test_flash_TP_phase_compositions_normalized(z, T):
    P_bub, _ = bubble_pressure(T, z)
    P = 0.6 * P_bub
    _, x, y = flash_TP(T, P, z)
    assert abs(float(np.sum(x)) - 1.0) < 1e-6
    assert abs(float(np.sum(y)) - 1.0) < 1e-6
    assert np.all(x >= -1e-12)
    assert np.all(y >= -1e-12)
