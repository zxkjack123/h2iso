"""Souers vapor pressure correlations for hydrogen isotopologues.

Implements the DIPPR 101 / PLXANT form:
    ln(P/Pa) = C1 + C2/T + C3*ln(T) + C4*T^C5

Parameters sourced from:
- Souers, P.C. "Hydrogen Properties for Fusion Energy" UCRL-52628 (1986)
- DIPPR database (H₂, D₂)
- Interpolation/estimation for HD, HT, DT (marked with higher uncertainty)

Valid range: triple point to critical point for each species.
"""

from __future__ import annotations

import json
import warnings
from typing import Union

import numpy as np

from h2iso._data import data_path

# Type alias for numeric inputs (numpy or scalar)
Numeric = Union[float, np.ndarray]


def _load_params() -> dict:
    """Load vapor pressure parameters from JSON."""
    with data_path("parameters", "vapor_pressure.json") as path:
        with open(path) as f:
            return json.load(f)["species"]


_PARAMS = _load_params()


def pvap(T: Numeric, species: str) -> Numeric:
    """Pure-component saturation pressure.

    Parameters
    ----------
    T : float or ndarray
        Temperature in Kelvin.
    species : str
        Species formula (H2, HD, HT, D2, DT, T2).

    Returns
    -------
    float or ndarray
        Saturation pressure in Pa.

    Raises
    ------
    ValueError
        If species is not recognized.

    Warns
    -----
    UserWarning
        If T is outside the valid correlation range.
    """
    if species not in _PARAMS:
        raise ValueError(
            f"Unknown species '{species}'. Valid: {list(_PARAMS.keys())}"
        )

    p = _PARAMS[species]
    T_arr = np.asarray(T, dtype=np.float64)

    # Range check
    T_min, T_max = p["T_min"], p["T_max"]
    if np.any(T_arr < T_min) or np.any(T_arr > T_max):
        warnings.warn(
            f"Temperature(s) outside valid range [{T_min}, {T_max}] K for {species}. "
            f"Results are extrapolated and may be inaccurate.",
            UserWarning,
            stacklevel=2,
        )

    # ln(P/Pa) = C1 + C2/T + C3*ln(T) + C4*T^C5
    ln_P = (
        p["C1"]
        + p["C2"] / T_arr
        + p["C3"] * np.log(T_arr)
        + p["C4"] * T_arr ** p["C5"]
    )

    result = np.exp(ln_P)

    # Return scalar if input was scalar
    if np.ndim(T) == 0:
        return float(result)
    return result


def dpvap_dT(T: Numeric, species: str) -> Numeric:
    """Temperature derivative of saturation pressure (dP/dT).

    Uses the Clausius-Clapeyron relation analytically:
        dP/dT = P * d(ln P)/dT

    Parameters
    ----------
    T : float or ndarray
        Temperature in Kelvin.
    species : str
        Species formula.

    Returns
    -------
    float or ndarray
        dPsat/dT in Pa/K.
    """
    if species not in _PARAMS:
        raise ValueError(
            f"Unknown species '{species}'. Valid: {list(_PARAMS.keys())}"
        )

    p = _PARAMS[species]
    T_arr = np.asarray(T, dtype=np.float64)

    # d(ln P)/dT = -C2/T^2 + C3/T + C4*C5*T^(C5-1)
    dln_P_dT = (
        -p["C2"] / T_arr**2
        + p["C3"] / T_arr
        + p["C4"] * p["C5"] * T_arr ** (p["C5"] - 1)
    )

    P = pvap(T_arr, species)
    result = P * dln_P_dT

    if np.ndim(T) == 0:
        return float(result)
    return result


def boiling_point(species: str) -> float:
    """Return the normal boiling point (at 101325 Pa) in K.

    Parameters
    ----------
    species : str
        Species formula.

    Returns
    -------
    float
        Normal boiling point in K.
    """
    if species not in _PARAMS:
        raise ValueError(
            f"Unknown species '{species}'. Valid: {list(_PARAMS.keys())}"
        )
    return _PARAMS[species]["T_boiling_101325Pa"]


def critical_point(species: str) -> tuple[float, float]:
    """Return critical temperature (K) and pressure (Pa).

    Parameters
    ----------
    species : str
        Species formula.

    Returns
    -------
    tuple of (Tc in K, Pc in Pa)
    """
    if species not in _PARAMS:
        raise ValueError(
            f"Unknown species '{species}'. Valid: {list(_PARAMS.keys())}"
        )
    p = _PARAMS[species]
    return p["T_critical"], p["P_critical_Pa"]


def triple_point(species: str) -> tuple[float, float]:
    """Return triple point temperature (K) and pressure (Pa).

    Parameters
    ----------
    species : str
        Species formula.

    Returns
    -------
    tuple of (Ttp in K, Ptp in Pa)
    """
    if species not in _PARAMS:
        raise ValueError(
            f"Unknown species '{species}'. Valid: {list(_PARAMS.keys())}"
        )
    p = _PARAMS[species]
    return p["T_triple"], p["P_triple_Pa"]


# CasADi-compatible version (lazy import)
def pvap_sx(T_sx, species: str):
    """CasADi SX symbolic vapor pressure.

    Parameters
    ----------
    T_sx : casadi.SX
        Symbolic temperature variable.
    species : str
        Species formula.

    Returns
    -------
    casadi.SX
        Symbolic expression for P(T) in Pa.
    """
    try:
        import casadi as ca
    except ImportError as e:
        raise ImportError(
            "CasADi is required for symbolic VLE. "
            "Install with: pip install h2iso[solver]"
        ) from e

    if species not in _PARAMS:
        raise ValueError(
            f"Unknown species '{species}'. Valid: {list(_PARAMS.keys())}"
        )

    p = _PARAMS[species]
    ln_P = (
        p["C1"]
        + p["C2"] / T_sx
        + p["C3"] * ca.log(T_sx)
        + p["C4"] * T_sx ** p["C5"]
    )
    return ca.exp(ln_P)
