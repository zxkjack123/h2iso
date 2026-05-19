"""Chemical equilibrium for hydrogen isotope exchange reactions.

At temperatures relevant to cryogenic distillation (14-35 K), catalytic
isotope exchange establishes equilibrium among the 6 hydrogen isotopologues
through 3 independent exchange reactions:

    H2 + D2 ⇌ 2HD    (K1)
    H2 + T2 ⇌ 2HT    (K2)
    D2 + T2 ⇌ 2DT    (K3)

Given total protium (H), deuterium (D), and tritium (T) atom fractions,
the equilibrium composition is uniquely determined.

References:
    - Jones, W.M. (1968). J. Chem. Phys. 48, 207.
    - Bigeleisen, J. & Mayer, M.G. (1947). J. Chem. Phys. 15, 261.
    - Souers, P.C. (1986). UCRL-52628, Chapter 5.
"""

from __future__ import annotations

import json

import numpy as np
from scipy.optimize import fsolve

from h2iso._data import data_path
from h2iso.species import N_SPECIES


def _load_eq_params() -> dict:
    with data_path("parameters", "equilibrium.json") as path:
        with open(path) as f:
            return json.load(f)


_EQ_PARAMS = _load_eq_params()


def keq(T: float, reaction: str) -> float:
    """Equilibrium constant for an exchange reaction.

    K_eq(T) = exp(a + b/T)

    Parameters
    ----------
    T : float
        Temperature in Kelvin.
    reaction : str
        Reaction identifier: 'H2_D2_2HD', 'H2_T2_2HT', or 'D2_T2_2DT'.

    Returns
    -------
    float
        Equilibrium constant (dimensionless).
    """
    rxns = _EQ_PARAMS["reactions"]
    if reaction not in rxns:
        raise ValueError(
            f"Unknown reaction '{reaction}'. "
            f"Available: {list(rxns.keys())}"
        )
    p = rxns[reaction]
    return float(np.exp(p["a"] + p["b"] / T))


def atom_fractions(x: np.ndarray) -> tuple[float, float, float]:
    """Convert mole fractions to atom fractions (H, D, T).

    Parameters
    ----------
    x : ndarray of shape (6,)
        Mole fractions in canonical order [H2, HD, HT, D2, DT, T2].

    Returns
    -------
    alpha_H, alpha_D, alpha_T : float
        Atom fractions (sum to 1).
    """
    x = np.asarray(x, dtype=np.float64)
    # Each molecule has 2 atoms:
    # H atoms: 2*H2 + 1*HD + 1*HT
    # D atoms: 1*HD + 2*D2 + 1*DT
    # T atoms: 1*HT + 1*DT + 2*T2
    H = 2 * x[0] + x[1] + x[2]
    D = x[1] + 2 * x[3] + x[4]
    T_atom = x[2] + x[4] + 2 * x[5]
    total = H + D + T_atom
    if total > 0:
        return H / total, D / total, T_atom / total
    return 0.0, 0.0, 0.0


def equilibrium_composition(
    alpha_H: float, alpha_D: float, alpha_T: float,
    T: float = 25.0
) -> np.ndarray:
    """Compute equilibrium mole fractions given atom fractions.

    Given total atom fractions and temperature, solves the equilibrium
    system to get the mole fractions of all 6 species.

    Parameters
    ----------
    alpha_H : float
        Hydrogen atom fraction (protium).
    alpha_D : float
        Deuterium atom fraction.
    alpha_T : float
        Tritium atom fraction.
    T : float
        Temperature in Kelvin (default: 25 K).

    Returns
    -------
    x_eq : ndarray of shape (6,)
        Equilibrium mole fractions [H2, HD, HT, D2, DT, T2].
    """
    # Validate inputs
    total = alpha_H + alpha_D + alpha_T
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Atom fractions must sum to 1, got {total}")

    # Normalize
    alpha_H /= total
    alpha_D /= total
    alpha_T /= total

    # Get equilibrium constants
    K1 = keq(T, "H2_D2_2HD")
    K2 = keq(T, "H2_T2_2HT")
    K3 = keq(T, "D2_T2_2DT")

    # Solve for mole fractions satisfying:
    # 1. Atom balance (H, D, T)
    # 2. Equilibrium relations: K1 = x_HD^2/(x_H2*x_D2), etc.
    # 3. Sum = 1

    # Use a parameterization: let h, d, t be effective "atom activities"
    # Then: x_H2 = h^2, x_D2 = d^2, x_T2 = t^2
    #        x_HD = sqrt(K1)*h*d, x_HT = sqrt(K2)*h*t, x_DT = sqrt(K3)*d*t
    # This automatically satisfies equilibrium. Then solve atom balance.

    def residuals(params):
        h, d, t = params
        # Mole fractions (unnormalized)
        x_H2 = h * h
        x_HD = np.sqrt(K1) * h * d
        x_HT = np.sqrt(K2) * h * t
        x_D2 = d * d
        x_DT = np.sqrt(K3) * d * t
        x_T2 = t * t

        # Total
        S = x_H2 + x_HD + x_HT + x_D2 + x_DT + x_T2

        # Atom fractions
        H_calc = (2 * x_H2 + x_HD + x_HT) / (2 * S)
        D_calc = (x_HD + 2 * x_D2 + x_DT) / (2 * S)
        T_calc = (x_HT + x_DT + 2 * x_T2) / (2 * S)

        return [H_calc - alpha_H, D_calc - alpha_D, T_calc - alpha_T]

    # Initial guess from ideal mixing (statistical limit)
    h0 = np.sqrt(max(alpha_H, 1e-20))
    d0 = np.sqrt(max(alpha_D, 1e-20))
    t0 = np.sqrt(max(alpha_T, 1e-20))

    params, info, ier, mesg = fsolve(
        residuals, [h0, d0, t0], full_output=True
    )
    if ier != 1:
        raise RuntimeError(
            f"Equilibrium solve failed (ier={ier}): {mesg.strip()} | "
            f"alpha=(H={alpha_H:.4g}, D={alpha_D:.4g}, T={alpha_T:.4g}), "
            f"T={T:.2f} K, final_residual_norm={np.linalg.norm(info['fvec']):.3e}"
        )
    h, d, t = params

    # Compute final mole fractions
    x = np.zeros(N_SPECIES)
    x[0] = h * h                     # H2
    x[1] = np.sqrt(K1) * h * d      # HD
    x[2] = np.sqrt(K2) * h * t      # HT
    x[3] = d * d                     # D2
    x[4] = np.sqrt(K3) * d * t      # DT
    x[5] = t * t                     # T2

    # Normalize
    x /= np.sum(x)

    # Clip tiny negatives from numerical noise
    x = np.maximum(x, 0.0)
    x /= np.sum(x)

    return x


def is_equilibrated(x: np.ndarray, T: float, rtol: float = 0.05) -> bool:
    """Check if a composition is at chemical equilibrium.

    Parameters
    ----------
    x : ndarray of shape (6,)
        Mole fractions.
    T : float
        Temperature in K.
    rtol : float
        Relative tolerance for equilibrium check.

    Returns
    -------
    bool
        True if composition satisfies equilibrium constraints within rtol.
    """
    x = np.asarray(x, dtype=np.float64)

    # Check K1: x_HD^2 / (x_H2 * x_D2) ≈ K1
    K1 = keq(T, "H2_D2_2HD")
    if x[0] > 1e-15 and x[3] > 1e-15:
        Q1 = x[1] ** 2 / (x[0] * x[3])
        if abs(Q1 / K1 - 1.0) > rtol:
            return False

    # Check K2: x_HT^2 / (x_H2 * x_T2) ≈ K2
    K2 = keq(T, "H2_T2_2HT")
    if x[0] > 1e-15 and x[5] > 1e-15:
        Q2 = x[2] ** 2 / (x[0] * x[5])
        if abs(Q2 / K2 - 1.0) > rtol:
            return False

    # Check K3: x_DT^2 / (x_D2 * x_T2) ≈ K3
    K3 = keq(T, "D2_T2_2DT")
    if x[3] > 1e-15 and x[5] > 1e-15:
        Q3 = x[4] ** 2 / (x[3] * x[5])
        if abs(Q3 / K3 - 1.0) > rtol:
            return False

    return True
