"""Atom conservation invariants for VLE equilibrium (T6.1).

H-isotopologue composition vectors over (H2, HD, HT, D2, DT, T2) carry
implicit atom counts. Total H/D/T atoms (per mol mixture) must be conserved
through any equilibrium operation that preserves overall mole balance.
"""

from __future__ import annotations

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from h2iso.species import N_SPECIES
from h2iso.vle.mixing import bubble_pressure, flash_TP

# Atom-count matrix A[atom, species] for SPECIES_ORDER = (H2, HD, HT, D2, DT, T2)
# row 0 = H atoms per molecule, row 1 = D, row 2 = T
_ATOM_MATRIX = np.array(
    [
        [2, 1, 1, 0, 0, 0],  # H
        [0, 1, 0, 2, 1, 0],  # D
        [0, 0, 1, 0, 1, 2],  # T
    ],
    dtype=np.float64,
)

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


def _atom_counts(comp: np.ndarray) -> np.ndarray:
    return _ATOM_MATRIX @ comp


@_PROFILE
@given(z=_compositions(), T=st.floats(min_value=23.0, max_value=27.0))
def test_flash_conserves_atoms(z, T):
    """Σ atoms in feed = Σ atoms in (1-V)x + V y (component split)."""
    P_bub, _ = bubble_pressure(T, z)
    P = 0.6 * P_bub
    V, x, y = flash_TP(T, P, z)
    atoms_feed = _atom_counts(z)
    atoms_out = (1.0 - V) * _atom_counts(x) + V * _atom_counts(y)
    rel = np.max(np.abs(atoms_out - atoms_feed) / np.maximum(atoms_feed, 1e-12))
    assert rel < 1e-6, (
        f"Atom conservation violated: feed={atoms_feed}, out={atoms_out}, rel={rel}"
    )


@_PROFILE
@given(x=_compositions(), T=st.floats(min_value=23.0, max_value=27.0))
def test_bubble_y_preserves_atom_fractions_sum(x, T):
    """Bubble vapour atom-fraction vector must sum to the same total atoms."""
    _, y = bubble_pressure(T, x)
    # Each mole of mixture has exactly 2 atoms (diatomic), independent of comp.
    assert abs(float(_atom_counts(y).sum()) - 2.0) < 1e-9
    assert abs(float(_atom_counts(x).sum()) - 2.0) < 1e-9
