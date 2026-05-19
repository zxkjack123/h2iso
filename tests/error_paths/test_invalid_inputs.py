"""Error path coverage: invalid inputs to public APIs (T6.2)."""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.mesh.enthalpy import liquid_enthalpy_numeric
from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.mixing import _validate_composition, bubble_pressure, flash_TP
from h2iso.vle.quantum import (
    acentric_factor,
    fugacity_correction,
    quantum_alpha_correction,
)
from h2iso.vle.souers import critical_point, pvap, triple_point


@pytest.fixture
def x_uniform() -> np.ndarray:
    return np.full(N_SPECIES, 1.0 / N_SPECIES)


def test_pvap_unknown_species():
    with pytest.raises(ValueError, match="Unknown species"):
        pvap(25.0, "ZZ")


def test_critical_point_unknown_species():
    with pytest.raises(ValueError, match="Unknown species"):
        critical_point("ZZ")


def test_triple_point_unknown_species():
    with pytest.raises(ValueError, match="Unknown species"):
        triple_point("ZZ")


def test_fugacity_correction_unknown_species():
    with pytest.raises(ValueError, match="Unknown species"):
        fugacity_correction(25.0, "ZZ")


def test_acentric_factor_unknown_species():
    with pytest.raises(ValueError, match="Unknown species"):
        acentric_factor("ZZ")


def test_quantum_alpha_correction_unknown_species():
    with pytest.raises(ValueError, match="Unknown species"):
        quantum_alpha_correction(25.0, "ZZ")


def test_quantum_alpha_correction_nonpositive_T():
    with pytest.raises(ValueError, match="T > 0"):
        quantum_alpha_correction(0.0, "H2")
    with pytest.raises(ValueError, match="T > 0"):
        quantum_alpha_correction(-1.0, "D2")


def test_validate_composition_wrong_shape():
    with pytest.raises(ValueError, match=f"{N_SPECIES} elements"):
        _validate_composition(np.zeros(N_SPECIES + 1))


def test_validate_composition_negative_value():
    bad = np.full(N_SPECIES, 1.0 / N_SPECIES)
    bad[0] = -0.5
    bad[1] = 1.0 / N_SPECIES + 0.5
    with pytest.raises(ValueError, match="Negative mole fractions"):
        _validate_composition(bad)


def test_validate_composition_bad_sum():
    bad = np.full(N_SPECIES, 0.05)  # sums to 0.3
    with pytest.raises(ValueError, match="sum to"):
        _validate_composition(bad)


def test_bubble_pressure_invalid_composition():
    with pytest.raises(ValueError):
        bubble_pressure(25.0, np.zeros(N_SPECIES + 1))


def test_flash_TP_invalid_feed():
    with pytest.raises(ValueError):
        flash_TP(25.0, 1.0e5, np.full(N_SPECIES, -0.5))


def test_liquid_enthalpy_nonpositive_T(x_uniform):
    with pytest.raises(ValueError):
        liquid_enthalpy_numeric(0.0, x_uniform)
    with pytest.raises(ValueError):
        liquid_enthalpy_numeric(-5.0, x_uniform)


