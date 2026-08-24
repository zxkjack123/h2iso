"""h2iso ISS-I single-case runner for parity comparison.

Solves the ISS-I three-column flowsheet with reduced stages (8-10)
for fast turnaround, and extracts H/D/T mass flows from the three
product streams (WDS, SDSD2, SDST2).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from h2iso.flowsheet.schema import load_flowsheet
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.parity.cases import atom_to_species

# Molar masses
_M_H = 1.008
_M_D = 2.014
_M_T = 3.016

# ISS-I JSON fixture (relative to src/h2iso/parity/)
_FIXTURE_ISS_I = (
    Path(__file__).parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "wang2022"
    / "iss_i.json"
)


def _composition_to_hdt(flow: float, x: np.ndarray) -> dict:
    """Convert species molar flow to H/D/T mass flows.

    flow: mol/h,  x: 6-element mole fraction [H2, HD, D2, HT, DT, T2]
    """
    Q = flow * np.asarray(x)
    H = (2 * Q[0] + Q[1] + Q[3]) * _M_H
    D = (Q[1] + 2 * Q[2] + Q[4]) * _M_D
    T = (Q[3] + Q[4] + 2 * Q[5]) * _M_T
    return {"H": float(H), "D": float(D), "T": float(T)}


def run_h2iso_iss_i(
    H_g_h: float,
    D_g_h: float,
    T_g_h: float,
    n_stages: int = 10,
    max_iter: int = 30,
    tol: float = 1e-3,
) -> dict:
    """Solve ISS-I for a given feed and return product H/D/T mass flows.

    Parameters
    ----------
    H_g_h, D_g_h, T_g_h : float
        Feed atom mass flows (g/h).
    n_stages : int
        Column stage count (reduced for speed; 10 = fast, 30+ = better accuracy).
    max_iter : int
        Max tear stream iterations.
    tol : float
        Convergence tolerance.

    Returns
    -------
    dict with keys:
        "feed_hdt": {"H": float, "D": float, "T": float}
        "feed_composition": dict (6 species)
        "feed_total_mol_h": float
        "products": {"WDS": {...}, "SDSD2": {...}, "SDST2": {...}}
        "converged": bool
        "iterations": int
        "tear_residual": float
        "solver_time_s": float
    """
    import time

    # Compute feed composition
    z = atom_to_species(H_g_h, D_g_h, T_g_h)

    # Compute total molar flow
    n_H = H_g_h / _M_H
    n_D = D_g_h / _M_D
    n_T = T_g_h / _M_T
    total_mol_h = (n_H + n_D + n_T) / 2.0  # each molecule has 2 atoms

    # Load base ISS-I config and scale stages
    config = load_flowsheet(_FIXTURE_ISS_I)
    for col in config.columns:
        col.n_stages = max(3, min(n_stages, col.n_stages))
    config.feeds[0].flow = total_mol_h
    config.feeds[0].composition = z

    # Solve
    solver = SequentialModularSolver(
        config,
        method="wegstein",
        continuation_substeps=0,
    )
    t0 = time.time()
    result = solver.solve(max_iter=max_iter, tol=tol)
    t1 = time.time()

    # Extract product flows
    products = {}
    cd1_dist = result.streams.get("CD1_distillate")
    cd2_dist = result.streams.get("CD2_distillate")
    cd3_bot = result.streams.get("CD3_bottoms")

    # WDS = combined CD1+CD2 distillate
    if cd1_dist is not None and cd2_dist is not None:
        wds_flow = cd1_dist.flow + cd2_dist.flow
        wds_x = np.array(
            cd1_dist.flow * np.asarray(cd1_dist.composition)
            + cd2_dist.flow * np.asarray(cd2_dist.composition)
        )
        wds_x = wds_x / wds_flow if wds_flow > 0 else np.zeros(6)
        products["WDS"] = _composition_to_hdt(wds_flow, wds_x)
    else:
        products["WDS"] = {"H": 0.0, "D": 0.0, "T": 0.0}

    # SDSD2 = CD2 distillate (D2-rich product)
    if cd2_dist is not None:
        products["SDSD2"] = _composition_to_hdt(
            cd2_dist.flow, np.asarray(cd2_dist.composition)
        )
    else:
        products["SDSD2"] = {"H": 0.0, "D": 0.0, "T": 0.0}

    # SDST2 = CD3 bottoms (T2-rich product)
    if cd3_bot is not None:
        products["SDST2"] = _composition_to_hdt(
            cd3_bot.flow, np.asarray(cd3_bot.composition)
        )
    else:
        products["SDST2"] = {"H": 0.0, "D": 0.0, "T": 0.0}

    return {
        "feed_hdt": {"H": H_g_h, "D": D_g_h, "T": T_g_h},
        "feed_composition": {
            "H2": float(z[0]),
            "HD": float(z[1]),
            "D2": float(z[2]),
            "HT": float(z[3]),
            "DT": float(z[4]),
            "T2": float(z[5]),
        },
        "feed_total_mol_h": total_mol_h,
        "products": products,
        "converged": result.converged,
        "iterations": result.iterations,
        "tear_residual": float(result.tear_residual),
        "solver_time_s": round(t1 - t0, 3),
    }
