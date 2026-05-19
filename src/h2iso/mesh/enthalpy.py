"""Enthalpy functions for hydrogen isotopologues.

Provides liquid and vapor molar enthalpies as CasADi SX expressions
for use in MESH energy balance equations. Reference state: saturated
liquid at the normal boiling point of D2 (23.661 K).
"""

from __future__ import annotations

import json

import casadi as ca
import numpy as np

from h2iso._data import data_path
from h2iso.species import SPECIES_ORDER


def _load_enthalpy_params() -> dict:
    with data_path("parameters", "enthalpy.json") as path:
        with open(path) as f:
            return json.load(f)


_PARAMS = _load_enthalpy_params()

# Reference temperature (NBP of D2)
T_REF = 23.661


def _vapor_cp_coeffs(species: str) -> tuple[float, float, float]:
    """Get Cp(T) = a + b*T + c*T² coefficients."""
    p = _PARAMS["vapor_cp"][species]
    return p["a"], p["b"], p["c"]


def _liquid_d(species: str) -> float:
    """Get liquid Cp correction parameter d."""
    return _PARAMS["liquid_cp_correction_d"][species]


def _hvap(species: str) -> float:
    """Get heat of vaporization at Tb [J/mol]."""
    return _PARAMS["heat_of_vaporization_Tb"][species]


def vapor_enthalpy_sx(T_sx: ca.SX, y: ca.SX) -> ca.SX:
    """Vapor molar enthalpy as CasADi SX expression.

    H_V(T, y) = Σ y_i * [∫_{T_ref}^{T} Cp_V_i dT + ΔHvap_i]

    Parameters
    ----------
    T_sx : casadi.SX
        Temperature (scalar symbol).
    y : casadi.SX of shape (6,)
        Vapor mole fractions.

    Returns
    -------
    casadi.SX
        Molar enthalpy [J/mol].
    """
    H = ca.SX(0)
    for i, sp in enumerate(SPECIES_ORDER):
        a, b, c = _vapor_cp_coeffs(sp)
        dH_vap = _hvap(sp)

        # Sensible heat: ∫_{T_ref}^T (a + b*T' + c*T'^2) dT'
        dT = T_sx - T_REF
        sensible = a * dT + 0.5 * b * (T_sx**2 - T_REF**2) + (c / 3) * (T_sx**3 - T_REF**3)

        # Total: sensible + latent (vapor is above liquid reference)
        H += y[i] * (sensible + dH_vap)

    return H


def liquid_enthalpy_sx(T_sx: ca.SX, x: ca.SX) -> ca.SX:
    """Liquid molar enthalpy as CasADi SX expression.

    H_L(T, x) = Σ x_i * ∫_{T_ref}^{T} Cp_L_i dT
    where Cp_L_i ≈ Cp_V_i * (1 + d_i/T)

    Parameters
    ----------
    T_sx : casadi.SX
        Temperature (scalar symbol).
    x : casadi.SX of shape (6,)
        Liquid mole fractions.

    Returns
    -------
    casadi.SX
        Molar enthalpy [J/mol].
    """
    H = ca.SX(0)
    for i, sp in enumerate(SPECIES_ORDER):
        a, b, c = _vapor_cp_coeffs(sp)
        d = _liquid_d(sp)

        # Cp_L = (a + b*T + c*T²) * (1 + d/T) ≈ a + a*d/T + b*T + ...
        # Simplified integral: ∫ Cp_L dT ≈ a*(T-Tref) + a*d*ln(T/Tref) + 0.5*b*(T²-Tref²)
        dT = T_sx - T_REF
        sensible = (a * dT + a * d * ca.log(T_sx / T_REF)
                    + 0.5 * b * (T_sx**2 - T_REF**2))

        H += x[i] * sensible

    return H


def vapor_enthalpy_numeric(T: float, y: np.ndarray) -> float:
    """Numeric vapor enthalpy evaluation (no CasADi dependency)."""
    H = 0.0
    for i, sp in enumerate(SPECIES_ORDER):
        a, b, c = _vapor_cp_coeffs(sp)
        dH_vap = _hvap(sp)
        dT = T - T_REF
        sensible = a * dT + 0.5 * b * (T**2 - T_REF**2) + (c / 3) * (T**3 - T_REF**3)
        H += y[i] * (sensible + dH_vap)
    return H


def liquid_enthalpy_numeric(T: float, x: np.ndarray) -> float:
    """Numeric liquid enthalpy evaluation (no CasADi dependency)."""
    if np.any(np.asarray(T) <= 0):
        raise ValueError(
            f"liquid_enthalpy_numeric requires T > 0 K (uses log(T/T_REF)); got T={T}"
        )
    H = 0.0
    for i, sp in enumerate(SPECIES_ORDER):
        a, b, c = _vapor_cp_coeffs(sp)
        d = _liquid_d(sp)
        dT = T - T_REF
        sensible = a * dT + a * d * np.log(T / T_REF) + 0.5 * b * (T**2 - T_REF**2)
        H += x[i] * sensible
    return H
