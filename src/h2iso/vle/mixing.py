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

import numpy as np
from scipy.optimize import brentq

from h2iso._data import data_path
from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.eos import EOS, IdealVLE
from h2iso.vle.souers import pvap


def _load_bip() -> np.ndarray:
    """Load BIP matrix from JSON."""
    with data_path("parameters", "bip.json") as path:
        with open(path, encoding="utf-8") as f:
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


def kvalue(
    T: float, P: float, x: np.ndarray | None = None, eos: EOS | None = None
) -> np.ndarray:
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
    K = eos.kvalue(T, P, x)
    if np.any(K <= 0):
        raise ValueError(
            f"K-values must be strictly positive; got K={np.asarray(K)} at "
            f"T={T} K, P={P} Pa"
        )
    return K


def bubble_pressure(
    T: float, x: np.ndarray, eos: EOS | None = None
) -> tuple[float, np.ndarray]:
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


def bubble_temperature(
    P: float, x: np.ndarray, eos: EOS | None = None
) -> tuple[float, np.ndarray]:
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

    # Compute the feasible V interval where every denominator 1 + V*(K_i - 1)
    # stays strictly positive.
    #   K_i > 1 (km1 > 0): denom = 1 + V*km1 > 0 for V > -1/km1 (a negative
    #     number); the constraint is automatic for V >= 0.
    #   K_i < 1 (km1 < 0): denom = 1 + V*km1 > 0 for V < -1/km1 = 1/(1-K_i),
    #     a positive upper bound on V.
    # The bubble/dew screens above already ensure V is in (0, 1); we just need
    # to keep V away from any denominator singularity below 1.
    km1 = K - 1
    neg_mask = km1 < 0
    V_low = 1e-10
    V_high = 1.0 - 1e-10

    if np.any(neg_mask):
        V_high = min(V_high, float(np.min(-1.0 / km1[neg_mask])) - 1e-10)

    if V_low >= V_high:
        raise ValueError(
            f"Rachford-Rice bracket invalid: V_low={V_low:.6g} >= V_high={V_high:.6g}. "
            f"Two-phase region indicated by bubble/dew checks but no feasible V; "
            f"K={K.tolist()}, z={z.tolist()}"
        )

    V = brentq(rr_residual, V_low, V_high, xtol=1e-12)
    return V


def flash_TP(
    T: float, P: float, z: np.ndarray, eos: EOS | None = None
) -> tuple[float, np.ndarray, np.ndarray]:
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


def rachford_rice_extended(
    z: np.ndarray, K: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    """Rachford-Rice allowing ``K = +inf`` (non-condensable components).

    Impurity extension: He-3 / He-4 are supercritical in the ISS window and are
    carried as ``K = inf``.  Such components go **entirely to the vapour
    phase**: with ``Z_inf`` their total feed fraction, the vapour fraction
    must satisfy ``V >= Z_inf``, and the residual becomes

        h(V) = sum_finite z_i (K_i - 1) / (1 + V (K_i - 1)) + Z_inf / V

    which is strictly decreasing in ``V`` on ``(Z_inf, 1]``.

    Parameters
    ----------
    z : ndarray
        Feed mole fractions (any length; need not be the 6-species set).
        Must be non-negative and sum to 1 (tolerance ``1e-6``).
    K : ndarray
        K-values.  Must be non-negative or ``+inf``; ``NaN``, negative values
        and ``-inf`` raise ``ValueError``.  ``0`` is legal (a strongly
        condensing species: the bubble criterion then holds and the feed goes
        entirely to the liquid endpoint).  Only ``+inf`` marks a
        non-condensable component.

    Returns
    -------
    (V, x, y) : (float, ndarray, ndarray)
        Vapour fraction (0 <= V <= 1) and phase compositions.  The endpoint
        contract is explicit:

        * all liquid (``V = 0``) -> ``(0.0, z.copy(), zeros_like(z))``.  This
          is returned whenever there is no non-condensable fraction and the
          bubble criterion ``sum(z_i K_i) <= 1`` holds; the ``sum(z_i K_i) == 1``
          bubble point is resolved as all liquid **by convention** (the guard
          is applied before the dew check).
        * all vapour (``V = 1``) -> ``(1.0, zeros_like(z), z.copy())``.

        For ``K = inf`` components ``x = 0`` and ``y = z / V`` (requires
        ``V > 0``; with ``Z_inf > 0`` this always holds).
    """
    z = np.asarray(z, dtype=np.float64)
    K = np.asarray(K, dtype=np.float64)
    if z.shape != K.shape:
        raise ValueError(f"z and K must have the same shape; got {z.shape}, {K.shape}")
    if np.any(np.isnan(K)):
        raise ValueError("K contains NaN")
    if np.any(K < 0.0):
        raise ValueError(
            "K must be non-negative (0 allowed) or +inf; got negative/-inf entries"
        )
    if np.any(z < 0):
        raise ValueError("feed mole fractions must be non-negative")
    z_sum = float(np.sum(z))
    if abs(z_sum - 1.0) > 1e-6:
        raise ValueError(f"feed mole fractions must sum to 1; got {z_sum}")

    inf_mask = np.isposinf(K)
    z_inf = float(np.sum(z[inf_mask]))
    if z_inf >= 1.0 - 1e-12:
        # everything non-condensable: all vapour
        return 1.0, np.zeros_like(z), z.copy()

    zf = z[~inf_mask]
    Kf = K[~inf_mask]

    # Bubble check on the finite subset (mirrors the classic solver, which
    # short-circuits to V = 0 when sum(z_i K_i) <= 1).  It must be tested
    # BEFORE the dew check so that the sum(z K) == 1 bubble boundary is
    # resolved as all-liquid by convention.  A non-condensable fraction
    # (z_inf > 0) forces vapour, so the guard only applies when z_inf == 0.
    sum_z_k = float(np.sum(zf * Kf)) if Kf.size else 0.0
    if z_inf == 0.0 and sum_z_k <= 1.0:
        return 0.0, z.copy(), np.zeros_like(z)

    def residual(V: float) -> float:
        return float(np.sum(zf * (Kf - 1.0) / (1.0 + V * (Kf - 1.0))) + z_inf / V)

    # dew check on the finite subset (K=inf terms never condense)
    with np.errstate(divide="ignore"):
        sum_z_over_k = float(np.sum(zf / Kf)) if Kf.size else 0.0
    if sum_z_over_k <= 1.0:
        # all vapour (consistent: non-condensables remain gaseous)
        return 1.0, np.zeros_like(z), z.copy()

    # two phase: root of the monotone residual in (z_inf, 1]
    v_hi = 1.0
    if residual(v_hi) >= 0.0:
        # even a fully vaporised stream leaves residual >= 0 -> all vapour
        return 1.0, np.zeros_like(z), z.copy()
    v_lo = z_inf + max(1e-12, 1e-9 * (1.0 - z_inf))
    if residual(v_lo) <= 0.0:  # numerically degenerate; fall back to midpoint
        v_lo = z_inf + 1e-6
    # bisection (robust; the problem is 1-D and smooth)
    a, b = v_lo, v_hi
    for _ in range(200):
        mid = 0.5 * (a + b)
        if residual(mid) > 0.0:
            a = mid
        else:
            b = mid
        if b - a < 1e-14:
            break
    V = 0.5 * (a + b)

    x = np.zeros_like(z)
    y = np.zeros_like(z)
    x[~inf_mask] = zf / (1.0 + V * (Kf - 1.0))
    y[~inf_mask] = Kf * x[~inf_mask]
    y[inf_mask] = z[inf_mask] / V
    x = np.clip(x, 0.0, None)
    y = np.clip(y, 0.0, None)
    # normalise tiny numerical drift
    if x.sum() > 0:
        x /= x.sum()
    if y.sum() > 0:
        y /= y.sum()
    return V, x, y
