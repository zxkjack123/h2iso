"""ISS-I test case definitions for three-way parity comparison.

Loads the 5 Aspen-baseline test cases (TC1-TC5) from the JSON fixture
and provides helper functions for feed composition calculation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Molar masses (g/mol) — must match the Aspen task spec
_M_H = 1.008
_M_D = 2.014
_M_T = 3.016

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "wang2022"
    / "iss_i_aspen_baseline.json"
)


def load_test_cases() -> list[dict]:
    """Return a list of 5 test case dicts (TC1-TC5)."""
    with open(FIXTURE_PATH) as f:
        return json.load(f)["test_cases"]


def get_feed_conditions(case: dict) -> dict:
    """Return feed H/D/T mass flows (g/h) and composition (6-species)."""
    return {
        "H_g_h": case["feed_atom_flow_g_h"]["H"],
        "D_g_h": case["feed_atom_flow_g_h"]["D"],
        "T_g_h": case["feed_atom_flow_g_h"]["T"],
        "composition": case["feed_composition"],
        "total_mol_h": case["feed_total_mol_h"],
    }


def get_products(case: dict) -> dict:
    """Return product stream H/D/T mass flows."""
    return case["products_atom_flow_g_h"]


def atom_to_species(H_g: float, D_g: float, T_g: float) -> np.ndarray:
    """Convert H/D/T mass flows (g/h) to 6-species mole fractions.

    Uses statistical equilibrium (random pairing) — same formula as Aspen task spec.
    """
    n_H = H_g / _M_H
    n_D = D_g / _M_D
    n_T = T_g / _M_T
    n_total = n_H + n_D + n_T
    if n_total <= 0:
        return np.zeros(6)
    x_H = n_H / n_total
    x_D = n_D / n_total
    x_T = n_T / n_total
    return np.array(
        [
            x_H**2,  # H2
            2 * x_H * x_D,  # HD
            x_D**2,  # D2
            2 * x_H * x_T,  # HT
            2 * x_D * x_T,  # DT
            x_T**2,  # T2
        ]
    )
