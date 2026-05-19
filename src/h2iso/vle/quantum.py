"""Quantum correction factors for hydrogen isotopologue thermodynamics.

At cryogenic temperatures (14-35 K), hydrogen isotopes exhibit significant
quantum mechanical effects that cause deviations from classical equations of state.
This module provides:
- de Boer quantum parameter (Λ*) for assessing quantum significance
- Feynman-Hibbs effective potential correction to fugacity
- Quantum-corrected alpha function for SRK EOS

References:
    - de Boer, J. (1948). Quantum theory of condensed permanent gases.
    - Feynman, R.P. & Hibbs, A.R. (1965). Quantum Mechanics and Path Integrals.
    - Sesé, L.M. (1993). Feynman-Hibbs potentials and path integrals.
    - Souers, P.C. (1986). UCRL-52628, Chapter 2.
"""

from __future__ import annotations

import json
from typing import Union

import numpy as np

from h2iso._data import data_path

Numeric = Union[float, np.ndarray]


def _load_quantum_params() -> dict:
    with data_path("parameters", "quantum.json") as path:
        with open(path) as f:
            return json.load(f)


_QPARAMS = _load_quantum_params()


def de_boer_parameter(species: str) -> float:
    """Return the reduced de Boer quantum parameter Λ*.

    Λ* = h / (σ * sqrt(m * ε))

    Values > 1 indicate significant quantum effects.
    All H-isotopologues have Λ* > 1.7 (strongly quantum).

    Parameters
    ----------
    species : str
        Species formula.

    Returns
    -------
    float
        Dimensionless de Boer parameter.
    """
    values = _QPARAMS["de_boer_lambda_star"]["values"]
    if species not in values:
        raise ValueError(f"Unknown species '{species}'.")
    return values[species]


def fugacity_correction(T: Numeric, species: str) -> Numeric:
    """Quantum correction factor for gas-phase fugacity coefficient.

    Based on second-order Feynman-Hibbs effective potential theory:
        φ_quantum / φ_classical = exp(α / T²)

    At 20 K, this correction is ~1% for T₂ and ~5-10% for H₂.

    Parameters
    ----------
    T : float or ndarray
        Temperature in Kelvin.
    species : str
        Species formula.

    Returns
    -------
    float or ndarray
        Multiplicative correction factor (dimensionless). >1 means quantum
        effects increase fugacity relative to classical prediction.
    """
    alphas = _QPARAMS["feynman_hibbs_correction"]["alpha_K2"]
    if species not in alphas:
        raise ValueError(f"Unknown species '{species}'.")

    alpha = alphas[species]
    T_arr = np.asarray(T, dtype=np.float64)
    correction = np.exp(alpha / T_arr**2)

    if np.ndim(T) == 0:
        return float(correction)
    return correction


def quantum_pvap_correction(T: Numeric, species: str) -> Numeric:
    """Quantum correction factor applied to vapor pressure.

    The vapor pressure of quantum fluids deviates from classical corresponding
    states prediction. This factor captures the leading-order quantum shift:
        P_actual ≈ P_classical * correction

    Parameters
    ----------
    T : float or ndarray
        Temperature in Kelvin.
    species : str
        Species formula.

    Returns
    -------
    float or ndarray
        Multiplicative correction factor for vapor pressure.
    """
    # For vapor pressure, the quantum effect manifests through both
    # liquid and vapor fugacity changes. The net effect on Psat is
    # approximately the inverse of the gas-phase correction:
    # Psat increases because quantum delocalization weakens liquid cohesion.
    return 1.0 / fugacity_correction(T, species)


def acentric_factor(species: str) -> float:
    """Return the acentric factor ω for a species.

    Note: H-isotopologues have NEGATIVE acentric factors due to quantum effects.
    Classical EOS (SRK/PR) with ω < 0 require modified alpha functions.

    Parameters
    ----------
    species : str
        Species formula.

    Returns
    -------
    float
        Acentric factor (dimensionless, typically negative for H-isotopes).
    """
    omegas = _QPARAMS["critical_properties_quantum_corrected"]["acentric_factor"]
    if species not in omegas:
        raise ValueError(f"Unknown species '{species}'.")
    return omegas[species]
