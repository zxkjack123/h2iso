"""Mixture VLE calculations for hydrogen isotopologues.

Provides:
- kij_matrix: Binary interaction parameters
- bubble_pressure / bubble_temperature: Bubble point calculations
- kvalue: K-value vector for a given T, P, composition
- flash_TP: Isothermal flash (Rachford-Rice)

All functions use modified Raoult's law with quantum corrections as default.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.eos import EOS, IdealVLE
from h2iso.vle.souers import pvap

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "parameters"


def _load_bip() -> np.ndarray:
    """Load BIP matrix from JSON."""
    path = _DATA_DIR / "bip.json"
    with open(path) as f:
        data = json.load(f)
    return np.array(data["kij"], dtype=np.float64)


_KIJ = _load_bip()


def kij_matrix() -> np.ndarray:
    """Return the 6x6 BIP matrix (symmetric, diagonal=0).

    Returns
    -------
    ndarray of shape (6, 6)
        Binary interaction parameters.
    """
    return _KIJ.copy()


def kvalue(T: float, P: float, x: np.ndarray | None = None,
           eos: EOS | None = None) -> np.ndarray:
    """Compute K-values for all 6 species.

    Parameters
    ----------
    T : float
        Temperature in K.
    P : float
        Pressure in Pa.
    x : ndarray of shape (6,), optional
        Liquid mole fractions (needed for activity coefficient models).
        For ideal/SRK at low P, not used but accepted for interface consistency.
    eos : EOS, optional
        Equation of state to use. Default: IdealVLE.

    Returns
    -------
    ndarray of shape (6,)
        K_i = y_i / x_i for each species.
    """
    if eos is None:
        eos = IdealVLE()
    if x is None:
        x = np.ones(N_SPECIES) / N_SPECIES
    return eos.kvalue(T, P, x)


def bubble_pressure(T: float, x: np.ndarray,
                    eos: EOS | None = None) -> tuple[float, np.ndarray]:
    """Calculate bubble point pressure and vapor composition.

    Parameters
    ----------
    T : float
        Temperature in K.
    x : ndarray of shape (6,)
        Liquid mole fractions (must sum to 1).

    Returns
    -------
    P_bubble : float
        Bubble point pressure in Pa.
    y : ndarray of shape (6,)
        Equilibrium vapor mole fractions.

    Raises
    ------
    ValueError
        If x contains negative values or doesn't sum to ~1.
    """
    x = np.asarray(x, dtype=np.float64)
    _validate_composition(x)

    if eos is None:
        eos = IdealVLE()

    # For ideal/modified Raoult's: P_bubble = Σ x_i * K_i * P
    # But K_i = Psat_i * φ_corr / P, so P_bubble = Σ x_i * Psat_i * φ_corr
    # Use iterative approach for generality
    K = eos.kvalue(T, 101325.0, x)  # initial guess at 1 atm
    P_bubble = np.sum(x * K * 101325.0)

    # For modified Raoult's law, we can compute directly:
    # P_bubble = Σ x_i * Psat_i * quantum_corr_i
    from h2iso.vle.quantum import fugacity_correction

    P_calc = 0.0
    for i, sp in enumerate(SPECIES_ORDER):
        if x[i] > 0:
            Psat_i = pvap(T, sp)
            phi_corr = fugacity_correction(T, sp)
            P_calc += x[i] * Psat_i * phi_corr

    P_bubble = P_calc

    # Vapor composition
    y = np.zeros(N_SPECIES)
    for i, sp in enumerate(SPECIES_ORDER):
        if x[i] > 0:
            Psat_i = pvap(T, sp)
            phi_corr = fugacity_correction(T, sp)
            y[i] = x[i] * Psat_i * phi_corr / P_bubble

    # Normalize (should already sum to 1, but ensure numerical consistency)
    y_sum = np.sum(y)
    if y_sum > 0:
        y /= y_sum

    return P_bubble, y


def bubble_temperature(P: float, x: np.ndarray,
                       eos: EOS | None = None) -> tuple[float, np.ndarray]:
    """Calculate bubble point temperature and vapor composition.

    Parameters
    ----------
    P : float
        Pressure in Pa.
    x : ndarray of shape (6,)
        Liquid mole fractions (must sum to 1).

    Returns
    -------
    T_bubble : float
        Bubble point temperature in K.
    y : ndarray of shape (6,)
        Equilibrium vapor mole fractions.
    """
    x = np.asarray(x, dtype=np.float64)
    _validate_composition(x)

    # Bracket the temperature using boiling points of present species
    from h2iso.vle.souers import boiling_point

    T_low = 14.0
    T_high = 35.0
    for i, sp in enumerate(SPECIES_ORDER):
        if x[i] > 0.01:
            Tb = boiling_point(sp)
            T_low = min(T_low, Tb - 3)
            T_high = max(T_high, Tb + 3)

    def objective(T):
        P_bub, _ = bubble_pressure(T, x, eos)
        return P_bub - P

    T_bubble = brentq(objective, T_low, T_high, xtol=1e-6)
    _, y = bubble_pressure(T_bubble, x, eos)
    return T_bubble, y


def rachford_rice(z: np.ndarray, K: np.ndarray) -> float:
    """Solve the Rachford-Rice equation for vapor fraction V.

    Σ z_i(K_i - 1) / (1 + V(K_i - 1)) = 0

    Parameters
    ----------
    z : ndarray
        Feed mole fractions.
    K : ndarray
        K-values.

    Returns
    -------
    V : float
        Vapor fraction (0 ≤ V ≤ 1). Returns 0 if subcooled, 1 if superheated.
    """
    z = np.asarray(z, dtype=np.float64)
    K = np.asarray(K, dtype=np.float64)

    # Check if we're in the two-phase region
    # Bubble check: Σ z_i * K_i > 1?
    if np.sum(z * K) <= 1.0:
        return 0.0  # Subcooled liquid
    # Dew check: Σ z_i / K_i > 1?
    with np.errstate(divide="ignore"):
        if np.sum(z / K) <= 1.0:
            return 1.0  # Superheated vapor

    def rr_residual(V):
        return np.sum(z * (K - 1) / (1 + V * (K - 1)))

    # Bounds for V to avoid division by zero
    # V must be in (V_min, V_max) where denominators stay positive
    km1 = K - 1
    neg_mask = km1 < 0
    pos_mask = km1 > 0

    V_min = 0.0
    V_max = 1.0

    if np.any(neg_mask):
        V_min = max(V_min, np.max(-1.0 / km1[neg_mask]) + 1e-10)
    if np.any(pos_mask):
        V_max = min(V_max, np.min(-1.0 / km1[pos_mask]) - 1e-10)

    # Ensure valid bounds
    V_min = max(V_min, 0.0)
    V_max = min(V_max, 1.0)

    if V_min >= V_max:
        return 0.5  # Fallback

    V = brentq(rr_residual, V_min, V_max, xtol=1e-12)
    return V


def flash_TP(T: float, P: float, z: np.ndarray,
             eos: EOS | None = None) -> tuple[float, np.ndarray, np.ndarray]:
    """Isothermal-isobaric (TP) flash calculation.

    Parameters
    ----------
    T : float
        Temperature in K.
    P : float
        Pressure in Pa.
    z : ndarray of shape (6,)
        Feed mole fractions (must sum to 1).

    Returns
    -------
    V : float
        Vapor fraction (mol vapor / mol feed).
    x : ndarray of shape (6,)
        Liquid mole fractions.
    y : ndarray of shape (6,)
        Vapor mole fractions.
    """
    z = np.asarray(z, dtype=np.float64)
    _validate_composition(z)

    K = kvalue(T, P, z, eos)
    V = rachford_rice(z, K)

    # Compute phase compositions
    if V <= 0.0:
        x = z.copy()
        y = z * K
        y /= np.sum(y)
    elif V >= 1.0:
        y = z.copy()
        with np.errstate(divide="ignore", invalid="ignore"):
            x = z / K
        x_sum = np.sum(x)
        if x_sum > 0:
            x /= x_sum
        else:
            x = z.copy()
    else:
        x = z / (1 + V * (K - 1))
        y = K * x
        # Normalize
        x /= np.sum(x)
        y /= np.sum(y)

    return V, x, y


def _validate_composition(x: np.ndarray) -> None:
    """Validate mole fraction array."""
    if x.shape != (N_SPECIES,):
        raise ValueError(f"Composition must have {N_SPECIES} elements, got {x.shape}")
    if np.any(x < -1e-10):
        neg_idx = np.where(x < 0)[0]
        neg_species = [SPECIES_ORDER[i] for i in neg_idx]
        raise ValueError(
            f"Negative mole fractions for: {neg_species} (values: {x[neg_idx]})"
        )
    total = np.sum(x)
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Mole fractions sum to {total}, expected ~1.0")
