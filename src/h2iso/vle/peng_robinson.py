"""Peng-Robinson Equation of State for hydrogen isotopologues.

Implements the PR cubic EOS with classical mixing rules for fugacity
coefficient computation.  Works as a drop-in replacement for the
Souers/IdealVLE K-value path in h2iso's numeric (non-CasADi) column
solver.

References
----------
Peng & Robinson (1976), Ind. Eng. Chem. Fundam. 15(1), 59-64.
Aspen Plus 14 Physical Property Methods, "Peng-Robinson."
"""

from __future__ import annotations

import numpy as np

from h2iso.species import N_SPECIES, SPECIES_ORDER

# ── Pure-component parameters for 6 H-isotopologues ──────────────────
# Critical temperature (K), critical pressure (Pa), acentric factor.
# Source: NIST REFPROP / Souers (1986) for H2/D2/T2;
#         estimated for HD/HT/DT via interpolation.
_PR_PARAMS: dict[str, tuple[float, float, float]] = {
    "H2": (33.145, 1296400.0, -0.219),
    "HD": (35.990, 1484000.0, -0.210),  # interpolated
    "HT": (37.440, 1552000.0, -0.205),  # interpolated
    "D2": (38.340, 1665000.0, -0.165),
    "DT": (40.000, 1740000.0, -0.155),  # interpolated
    "T2": (40.440, 1856000.0, -0.148),
}

# Gas constant (J/(mol·K))
_R = 8.314462618


def _alpha(T: float, Tc: float, omega: float) -> float:
    """Temperature-dependent α(Tr) for the attractive term."""
    Tr = T / Tc
    kappa = 0.37464 + 1.54226 * omega - 0.26992 * omega**2
    return (1.0 + kappa * (1.0 - np.sqrt(Tr))) ** 2


def _mixture_a(
    T: float, x: np.ndarray, kij: np.ndarray | None = None
) -> tuple[float, np.ndarray, np.ndarray]:
    """Compute mixture attractive parameter a_mix.

    Returns
    -------
    a_mix : float
    ai : ndarray, per-component a_i
    aij : ndarray (Nc, Nc), pair-wise a_ij
    """
    Nc = len(x)
    ai = np.zeros(Nc)
    bi = np.zeros(Nc)
    for i, sp in enumerate(SPECIES_ORDER[:Nc]):
        Tc, Pc, omega = _PR_PARAMS[sp]
        ai[i] = 0.45724 * (_R**2) * (Tc**2) / Pc * _alpha(T, Tc, omega)
        bi[i] = 0.07780 * _R * Tc / Pc

    if kij is None:
        kij = np.zeros((Nc, Nc))

    a_mix = 0.0
    aij = np.zeros((Nc, Nc))
    for i in range(Nc):
        for j in range(Nc):
            aij[i, j] = np.sqrt(ai[i] * ai[j]) * (1.0 - kij[i, j])
            a_mix += x[i] * x[j] * aij[i, j]

    return a_mix, ai, aij


def _mixture_b(x: np.ndarray) -> tuple[float, np.ndarray]:
    """Compute mixture co-volume parameter b_mix."""
    Nc = len(x)
    bi = np.zeros(Nc)
    for i, sp in enumerate(SPECIES_ORDER[:Nc]):
        Tc, Pc, _ = _PR_PARAMS[sp]
        bi[i] = 0.07780 * _R * Tc / Pc

    b_mix = np.sum(x * bi)
    return b_mix, bi


def _cubic_roots(a: float, b: float, c: float) -> np.ndarray:
    """Find roots of z³ + a*z² + b*z + c = 0 using Cardano's formula.

    Returns only real roots.
    """
    Q = (a**2 - 3 * b) / 9.0
    R = (2 * a**3 - 9 * a * b + 27 * c) / 54.0
    M = Q**3 - R**2

    roots = []
    if M >= 0:  # three real roots
        theta = np.arccos(R / np.sqrt(Q**3))
        for k in range(3):
            z_k = -2 * np.sqrt(Q) * np.cos((theta + 2 * np.pi * k) / 3.0) - a / 3.0
            roots.append(z_k)
    else:  # one real root
        S = np.sign(R) * np.abs(R + np.sqrt(-M)) ** (1 / 3)
        if abs(S) < 1e-30:
            T = 0.0
        else:
            T = Q / S
        z_k = S + T - a / 3.0
        roots.append(z_k)

    return np.array([r for r in roots if np.isreal(r)], dtype=float)


def _z_factor(T: float, P: float, x: np.ndarray) -> tuple[float, float]:
    """Solve PR cubic EOS for compressibility factor Z.

    Returns
    -------
    Z_liquid, Z_vapor : float
        Liquid and vapor root of the cubic (min and max positive roots).
    """
    _, ai, _ = _mixture_a(T, x)
    b_mix, bi = _mixture_b(x)
    a_mix, _, aij = _mixture_a(T, x)

    A = a_mix * P / (_R**2 * T**2)
    B = b_mix * P / (_R * T)

    # PR cubic: Z³ - (1-B)Z² + (A-3B²-2B)Z - (AB-B²-B³) = 0
    a_coeff = -(1.0 - B)
    b_coeff = A - 3 * B**2 - 2 * B
    c_coeff = -(A * B - B**2 - B**3)

    roots = _cubic_roots(a_coeff, b_coeff, c_coeff)
    if len(roots) == 0:
        return 1.0, 1.0  # ideal gas fallback

    Z_min = float(np.min(roots[roots > 0]) if np.any(roots > 0) else 1.0)
    Z_max = float(np.max(roots[roots > 0]) if np.any(roots > 0) else 1.0)

    return Z_min, Z_max


def fugacity_coefficient(
    T: float, P: float, x: np.ndarray, phase: str = "liquid"
) -> np.ndarray:
    """Compute fugacity coefficients φ_i for each component.

    Parameters
    ----------
    T, P, x : as usual
    phase : "liquid" or "vapor"

    Returns
    -------
    ndarray of shape (6,)
        φ_i = f_i / (x_i * P)
    """
    x = np.asarray(x, dtype=float)
    x = x / x.sum()
    Nc = len(x)

    b_mix, bi = _mixture_b(x)
    a_mix, ai, aij = _mixture_a(T, x)

    Z_l, Z_v = _z_factor(T, P, x)
    Z = Z_l if phase == "liquid" else Z_v

    A = a_mix * P / (_R**2 * T**2)
    B = b_mix * P / (_R * T)

    ln_phi = np.zeros(Nc)
    for i in range(Nc):
        # Partial molar a-derivative: ā_i = 2 * Σ_j x_j * a_ij
        a_bar_i = 0.0
        for j in range(Nc):
            a_bar_i += x[j] * aij[i, j]
        a_bar_i *= 2.0

        ln_phi[i] = (
            bi[i] / b_mix * (Z - 1.0)
            - np.log(Z - B)
            - A
            / (2.0 * np.sqrt(2.0) * B)
            * (a_bar_i / a_mix - bi[i] / b_mix)
            * np.log((Z + (1.0 + np.sqrt(2.0)) * B) / (Z + (1.0 - np.sqrt(2.0)) * B))
        )

    return np.exp(ln_phi)


def kvalue(T: float, P: float, x: np.ndarray) -> np.ndarray:
    """Compute K-values = φ_L / φ_V for all species.

    Uses the PR EOS to compute fugacity coefficients in both phases.
    The VLE condition y_i * φ_V_i = x_i * φ_L_i gives K_i = φ_L_i / φ_V_i.
    """
    phi_L = fugacity_coefficient(T, P, x, phase="liquid")
    phi_V = fugacity_coefficient(T, P, x, phase="vapor")

    K = np.zeros(N_SPECIES)
    for i in range(N_SPECIES):
        if x[i] > 1e-15:
            K[i] = phi_L[i] / (phi_V[i] + 1e-30)
        else:
            K[i] = 1.0

    K = np.where(K > 0, K, 0.01)
    K = np.where(K < 100, K, 100.0)

    return K
