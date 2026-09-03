"""Tritium inventory calculation algorithms for distillation columns.

Implements the 6-zone (VC, VP, VR, LC, LP, LR) inventory evaluation from:
    X. Wang, Q. Zeng, W. Shi, H. Chen, "Hydrogen isotope inventory evaluation of
    hydrogen isotopes separation system of CFETR using Aspen Plus simulator",
    Fusion Engineering and Design, vol. 177 (2022) 113078.
    DOI: https://doi.org/10.1016/j.fusengdes.2022.113078
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np

from h2iso.inventory.models import (
    DEFAULT_MOLAR_VOLUMES,
    DEFAULT_TRITIUM_EQUIVALENCE,
    R_GAS,
    ColumnInventoryResult,
    FlowsheetInventoryResult,
    InventoryGeometry,
)
from h2iso.mesh.column import ColumnResult
from h2iso.species import SPECIES_ORDER


def evaluate_column_inventory(
    result: ColumnResult,
    geometry: InventoryGeometry | None = None,
    pressure: float | tuple[float, float] | np.ndarray = 101325.0,
    column_name: str = "Column",
    molar_volumes: dict[str, float] | None = None,
    tritium_equivalence: dict[str, float] | None = None,
) -> ColumnInventoryResult:
    """Calculate the tritium inventory breakdown for a single distillation column.

    Parameters
    ----------
    result : ColumnResult
        Solved column state containing T_profile, x_profile, y_profile.
    geometry : InventoryGeometry, optional
        Column dimensions and liquid/packing void fractions.
    pressure : float or tuple (P_top, P_bottom) or array of shape (N,)
        Stage pressure(s) in Pa.
    column_name : str
        Identifier name for the column.
    molar_volumes : dict, optional
        Liquid molar volumes per species [m^3/mol].
    tritium_equivalence : dict, optional
        Tritium equivalence factor per species (alpha_i).

    Returns
    -------
    ColumnInventoryResult
    """
    if geometry is None:
        geometry = InventoryGeometry()

    if molar_volumes is None:
        molar_volumes = DEFAULT_MOLAR_VOLUMES

    if tritium_equivalence is None:
        tritium_equivalence = DEFAULT_TRITIUM_EQUIVALENCE

    # Vector of alpha_i in canonical order (H2, HD, HT, D2, DT, T2)
    alpha = np.array([tritium_equivalence.get(sp, 0.0) for sp in SPECIES_ORDER], dtype=np.float64)

    # Vector of liquid molar volumes v_i in canonical order
    v_mol = np.array([molar_volumes.get(sp, 2.5e-5) for sp in SPECIES_ORDER], dtype=np.float64)

    N = len(result.T_profile)
    if N < 2:
        raise ValueError(f"Column must have at least 2 stages; got {N}")

    # Build pressure profile P_j
    if isinstance(pressure, (tuple, list)) and len(pressure) == 2:
        P_prof = np.linspace(pressure[0], pressure[1], N)
    elif isinstance(pressure, np.ndarray) and pressure.shape == (N,):
        P_prof = pressure.copy()
    else:
        P_prof = np.full(N, float(pressure))

    T_prof = result.T_profile
    x_prof = result.x_profile
    y_prof = result.y_profile

    # Volume per theoretical stage in packed section [m^3]
    # V_stage = pi * (D / 2)^2 * HETP
    cross_section_area = math.pi * (geometry.inside_diameter_m / 2.0) ** 2
    V_stage = cross_section_area * geometry.HETP_m

    stage_gas_inv = np.zeros(N)
    stage_liq_inv = np.zeros(N)

    # --- 1. Condenser (Stage index 0) ---
    # Gas phase (Eq. 8): H_VC = sum_i [ P1 * V1 * (1 - eps1) / (R * T1) * y1,i * alpha_i ]
    sum_y_alpha_0 = float(np.dot(y_prof[0], alpha))
    H_VC = (P_prof[0] * geometry.condenser_volume_m3 * (1.0 - geometry.eps_condenser)
            / (R_GAS * T_prof[0])) * sum_y_alpha_0

    # Liquid phase (Eq. 12): H_LC = [ V1 * eps1 / (sum_k x1,k * v_k) ] * (sum_i x1,i * alpha_i)
    v_avg_0 = max(float(np.dot(x_prof[0], v_mol)), 1e-10)
    sum_x_alpha_0 = float(np.dot(x_prof[0], alpha))
    H_LC = (geometry.condenser_volume_m3 * geometry.eps_condenser / v_avg_0) * sum_x_alpha_0

    stage_gas_inv[0] = H_VC
    stage_liq_inv[0] = H_LC

    # --- 2. Packed Section (Stages 1 to N-2) ---
    # For j in 1..N-2 (0-indexed, corresponding to stages 2..N-1 in 1-indexed)
    H_VP = 0.0
    H_LP = 0.0

    # Packing gas void factor: 1 - eps * (1 + eps_j)
    gas_void_factor = 1.0 - geometry.eps_packing * (1.0 + geometry.eps_stage)
    # Packing liquid volume factor: V_stage * eps * eps_j
    liq_vol_factor = V_stage * geometry.eps_packing * geometry.eps_stage

    for j in range(1, N - 1):
        # Gas (Eq. 9)
        sum_y_alpha_j = float(np.dot(y_prof[j], alpha))
        H_VP_j = (P_prof[j] * V_stage * gas_void_factor / (R_GAS * T_prof[j])) * sum_y_alpha_j
        H_VP += H_VP_j
        stage_gas_inv[j] = H_VP_j

        # Liquid (Eq. 13)
        v_avg_j = max(float(np.dot(x_prof[j], v_mol)), 1e-10)
        sum_x_alpha_j = float(np.dot(x_prof[j], alpha))
        H_LP_j = (liq_vol_factor / v_avg_j) * sum_x_alpha_j
        H_LP += H_LP_j
        stage_liq_inv[j] = H_LP_j

    # --- 3. Reboiler (Stage index N-1) ---
    # Gas phase (Eq. 10): H_VR = sum_i [ PN * VN * (1 - epsN) / (R * TN) * yN,i * alpha_i ]
    sum_y_alpha_N = float(np.dot(y_prof[-1], alpha))
    H_VR = (P_prof[-1] * geometry.reboiler_volume_m3 * (1.0 - geometry.eps_reboiler)
            / (R_GAS * T_prof[-1])) * sum_y_alpha_N

    # Liquid phase (Eq. 14): H_LR = [ VN * epsN / (sum_k xN,k * v_k) ] * (sum_i xN,i * alpha_i)
    v_avg_N = max(float(np.dot(x_prof[-1], v_mol)), 1e-10)
    sum_x_alpha_N = float(np.dot(x_prof[-1], alpha))
    H_LR = (geometry.reboiler_volume_m3 * geometry.eps_reboiler / v_avg_N) * sum_x_alpha_N

    stage_gas_inv[-1] = H_VR
    stage_liq_inv[-1] = H_LR

    return ColumnInventoryResult(
        column_name=column_name,
        gas_condenser_mol=float(H_VC),
        gas_packed_mol=float(H_VP),
        gas_reboiler_mol=float(H_VR),
        liquid_condenser_mol=float(H_LC),
        liquid_packed_mol=float(H_LP),
        liquid_reboiler_mol=float(H_LR),
        stage_gas_inventory_mol=stage_gas_inv,
        stage_liquid_inventory_mol=stage_liq_inv,
    )


def evaluate_flowsheet_inventory(
    flowsheet_result: Any,
    flowsheet_config: Any,
    geometries: dict[str, InventoryGeometry] | None = None,
) -> FlowsheetInventoryResult:
    """Calculate tritium inventory across all columns in a flowsheet result.

    Parameters
    ----------
    flowsheet_result : FlowsheetResult
        Solved flowsheet result containing column_results mapping.
    flowsheet_config : FlowsheetConfig
        Flowsheet configuration containing column definitions.
    geometries : dict[str, InventoryGeometry], optional
        Optional per-column geometry override dictionary.

    Returns
    -------
    FlowsheetInventoryResult
    """
    if geometries is None:
        geometries = {}

    col_cfg_map = {c.name: c for c in flowsheet_config.columns}
    results = {}

    for name, cr in flowsheet_result.column_results.items():
        if cr is None:
            continue

        cfg = col_cfg_map.get(name)
        geom = geometries.get(name)

        if geom is None and cfg is not None:
            # Build InventoryGeometry from ColumnConfig attributes if available
            geom = InventoryGeometry(
                inside_diameter_m=getattr(cfg, "inside_diameter_m", 0.05),
                HETP_m=getattr(cfg, "HETP_m", 0.05),
                condenser_volume_m3=getattr(cfg, "condenser_volume_m3", 1.0e-3),
                reboiler_volume_m3=getattr(cfg, "reboiler_volume_m3", 2.0e-4),
            )
        elif geom is None:
            warnings.warn(
                f"Column '{name}' not found in flowsheet config and no custom geometry provided; "
                f"falling back to default InventoryGeometry (D=0.05m, HETP=0.05m).",
                UserWarning,
                stacklevel=2,
            )
            geom = InventoryGeometry()

        # Pressure
        if cfg is None:
            warnings.warn(
                f"Column '{name}' not found in flowsheet config; "
                f"falling back to default pressure (101325 Pa).",
                UserWarning,
                stacklevel=2,
            )
        p_top = getattr(cfg, "pressure_top_Pa", getattr(cfg, "pressure", 101325.0))
        p_bot = getattr(cfg, "pressure_bottom_Pa", getattr(cfg, "pressure", 101325.0))
        pressure = (p_top, p_bot)

        inv_res = evaluate_column_inventory(
            result=cr,
            geometry=geom,
            pressure=pressure,
            column_name=name,
        )
        results[name] = inv_res

    return FlowsheetInventoryResult(columns=results)
