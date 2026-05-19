"""Property-based VLE invariants (T6.1)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from h2iso.species import N_SPECIES
from h2iso.vle.mixing import bubble_pressure

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
@given(x=_compositions(), T=st.floats(min_value=22.0, max_value=28.0))
def test_bubble_pressure_yields_normalized_vapor(x, T):
    P_bub, y = bubble_pressure(T, x)
    assert P_bub > 0
    assert abs(float(np.sum(y)) - 1.0) < 1e-9
    assert np.all(y >= -1e-12)


@_PROFILE
@given(x=_compositions(), T_lo=st.floats(min_value=22.0, max_value=25.0))
def test_bubble_pressure_monotone_in_T(x, T_lo):
    T_hi = T_lo + 2.0
    P_lo, _ = bubble_pressure(T_lo, x)
    P_hi, _ = bubble_pressure(T_hi, x)
    assert P_hi > P_lo, (
        f"bubble pressure not monotone in T: P({T_lo})={P_lo:.3e}, P({T_hi})={P_hi:.3e}"
    )


@_PROFILE
@given(x=_compositions(), T=st.floats(min_value=22.0, max_value=28.0))
def test_bubble_pressure_within_pure_envelope(x, T):
    """Bubble P must lie between the smallest and largest pure-component Psat."""
    from h2iso.species import SPECIES_ORDER
    from h2iso.vle.souers import pvap

    P_bub, _ = bubble_pressure(T, x)
    psats = np.array([pvap(T, sp) for sp in SPECIES_ORDER])
    # Allow tolerance for quantum fugacity correction (a few percent)
    assert P_bub >= 0.9 * psats.min()
    assert P_bub <= 1.1 * psats.max()
