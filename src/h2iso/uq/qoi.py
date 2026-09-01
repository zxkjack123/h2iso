"""Quantity-of-Interest (QoI) extraction from FlowsheetResult.

Each QoI function takes a :class:`~h2iso.flowsheet.solver.FlowsheetResult`
(or a :class:`~h2iso.mesh.column.ColumnResult` for single-column mode)
and returns a flat 1-D array of floats.  The caller assembles these into
the design matrix used by the Sobol / MC post-processors.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from h2iso.species import N_SPECIES, SPECIES_ORDER


class _SupportsColumnResults(Protocol):
    """Minimal structural type for FlowsheetResult."""

    converged: bool
    iterations: int
    tear_residual: float
    streams: dict
    column_results: dict


class _SupportsColumnResult(Protocol):
    """Minimal structural type for ColumnResult."""

    T_profile: np.ndarray
    x_profile: np.ndarray
    y_profile: np.ndarray
    condenser_duty: float
    reboiler_duty: float
    convergence_info: dict


def _get_column_result(
    obj: _SupportsColumnResults | _SupportsColumnResult,
    column_name: str | None = None,
) -> _SupportsColumnResult:
    """Return a ColumnResult from either a FlowsheetResult or a bare ColumnResult."""
    if hasattr(obj, "column_results"):
        # FlowsheetResult
        if column_name is None:
            # Pick the first available column
            if not obj.column_results:
                raise ValueError("FlowsheetResult has no column_results")
            column_name = next(iter(obj.column_results))
        cr = obj.column_results.get(column_name)
        if cr is None:
            raise KeyError(
                f"Column '{column_name}' not found in FlowsheetResult.column_results "
                f"(available: {list(obj.column_results)})"
            )
        return cr
    # Assume it's already a ColumnResult
    return obj  # type: ignore[return-value]


def qoi_default(
    obj: _SupportsColumnResults | _SupportsColumnResult,
    column_name: str | None = None,
) -> np.ndarray:
    """Default QoI vector.

    Extracts:
    - Top product composition (N_SPECIES values)
    - Bottom product composition (N_SPECIES values)
    - Condenser duty (1)
    - Reboiler duty (1)
    - Top temperature (1)
    - Bottom temperature (1)

    Total length: ``2 * N_SPECIES + 4``
    """
    cr = _get_column_result(obj, column_name)
    x_top = np.asarray(cr.x_profile[0], dtype=float)
    x_bot = np.asarray(cr.x_profile[-1], dtype=float)
    T_top = float(cr.T_profile[0])
    T_bot = float(cr.T_profile[-1])
    Q_cond = float(cr.condenser_duty)
    Q_reb = float(cr.reboiler_duty)
    return np.concatenate(
        [
            x_top,  # 6
            x_bot,  # 6
            [Q_cond, Q_reb],  # 2
            [T_top, T_bot],  # 2
        ]
    )


def qoi_labels(column_name: str = "") -> list[str]:
    """Human-readable labels for the default QoI vector."""
    prefix = f"{column_name}." if column_name else ""
    return (
        [f"{prefix}x_top[{sp}]" for sp in SPECIES_ORDER]
        + [f"{prefix}x_bot[{sp}]" for sp in SPECIES_ORDER]
        + [f"{prefix}Q_condenser_W", f"{prefix}Q_reboiler_W"]
        + [f"{prefix}T_top_K", f"{prefix}T_bottom_K"]
    )


def qoi_separation_factor(
    obj: _SupportsColumnResults | _SupportsColumnResult,
    light_key: str = "D2",
    heavy_key: str = "DT",
    column_name: str | None = None,
) -> np.ndarray:
    """Separation factor alpha = (x_LK_top / x_HK_top) / (x_LK_bot / x_HK_bot).

    Returns a length-1 array.
    """
    cr = _get_column_result(obj, column_name)
    i_lk = SPECIES_ORDER.index(light_key)
    i_hk = SPECIES_ORDER.index(heavy_key)
    x_top = np.asarray(cr.x_profile[0], dtype=float)
    x_bot = np.asarray(cr.x_profile[-1], dtype=float)

    eps = 1e-30
    alpha = ((x_top[i_lk] + eps) / (x_top[i_hk] + eps)) / (
        (x_bot[i_lk] + eps) / (x_bot[i_hk] + eps)
    )
    return np.array([alpha])


def qoi_convergence(
    obj: _SupportsColumnResults,
) -> np.ndarray:
    """Convergence diagnostics: [converged, iterations, tear_residual]."""
    return np.array(
        [
            float(obj.converged),
            float(obj.iterations),
            float(obj.tear_residual),
        ]
    )


def qoi_n_components() -> int:
    """Number of elements in :func:`qoi_default`."""
    return 2 * N_SPECIES + 4


def _stream_product_composition(streams: dict, prefix: str) -> np.ndarray:
    """Extract composition from ``{prefix}_distillate`` and
    ``{prefix}_bottoms`` streams."""
    top = streams.get(f"{prefix}_distillate")
    bot = streams.get(f"{prefix}_bottoms")
    x_top = (
        np.asarray(top.composition, dtype=float)
        if top is not None
        else np.full(N_SPECIES, np.nan)
    )
    x_bot = (
        np.asarray(bot.composition, dtype=float)
        if bot is not None
        else np.full(N_SPECIES, np.nan)
    )
    T_top = float(top.temperature) if top is not None else np.nan
    T_bot = float(bot.temperature) if bot is not None else np.nan
    F_top = float(top.flow) if top is not None else np.nan
    F_bot = float(bot.flow) if bot is not None else np.nan
    return np.concatenate([x_top, x_bot, [T_top, T_bot, F_top, F_bot]])


def qoi_isso_products(
    obj: _SupportsColumnResults,
) -> np.ndarray:
    """ISS-O flowsheet QoI: product purities + temps + flows for CD1/CD2/CD3.

    Returns a vector of length ``3 * (2 * N_SPECIES + 4)`` = 48.
    """
    streams = obj.streams
    parts = []
    for col in ("CD1", "CD2", "CD3"):
        parts.append(_stream_product_composition(streams, col))
    return np.concatenate(parts)


def qoi_isso_labels() -> list[str]:
    """Labels for :func:`qoi_isso_products`."""
    labels = []
    for col in ("CD1", "CD2", "CD3"):
        labels += qoi_labels(col)
        labels += [f"{col}.F_top_mol_h", f"{col}.F_bot_mol_h"]
    return labels


def qoi_isso_compact(
    obj: _SupportsColumnResults,
) -> np.ndarray:
    """Compact ISS-O QoI: key product purities + temps + convergence.

    Returns a vector of length 13:
    [CD1_top_H2_dilution, CD2_top_H2, CD3_bot_T2, T_top×3, T_bot×3,
     Q_cond×3, converged]
    """
    streams = obj.streams
    crs = obj.column_results if hasattr(obj, "column_results") else {}
    parts = []

    # CD1 top H2 purity
    cd1 = streams.get("CD1_distillate")
    parts.append(cd1.composition[0] if cd1 else np.nan)

    # CD2 top H2 purity
    cd2 = streams.get("CD2_distillate")
    parts.append(cd2.composition[0] if cd2 else np.nan)

    # CD3 bottom T2 purity
    cd3 = streams.get("CD3_bottoms")
    parts.append(cd3.composition[5] if cd3 else np.nan)

    # Temperatures
    for col in ("CD1", "CD2", "CD3"):
        cr = crs.get(col)
        if cr is not None:
            parts.append(float(cr.T_profile[0]))
            parts.append(float(cr.T_profile[-1]))
        else:
            parts.extend([np.nan, np.nan])

    # Condenser duties
    for col in ("CD1", "CD2", "CD3"):
        cr = crs.get(col)
        parts.append(float(cr.condenser_duty) if cr is not None else np.nan)

    # Convergence
    parts.append(float(obj.converged))

    return np.array(parts, dtype=float)


def qoi_isso_compact_labels() -> list[str]:
    """Labels for :func:`qoi_isso_compact`."""
    return [
        "CD1_top_H2",
        "CD2_top_H2",
        "CD3_bot_T2",
        "CD1_T_top_K",
        "CD1_T_bot_K",
        "CD2_T_top_K",
        "CD2_T_bot_K",
        "CD3_T_top_K",
        "CD3_T_bot_K",
        "CD1_Q_cond_W",
        "CD2_Q_cond_W",
        "CD3_Q_cond_W",
        "converged",
    ]
