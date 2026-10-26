"""Stage-efficiency models for the MESH column solver (holdup/efficiency extension).

Two distinct concepts are supported, and they are intentionally **not**
interchangeable (see the cited design note):

``"murphree"`` -- Murphree vapour efficiency
    Describes how far the vapour *leaving* a stage approaches the vapour
    composition in equilibrium with the liquid leaving that stage:

        E_MV,j = (y_j - y_in) / (y*_j - y_in),    y*_j = K_j x_j

    where ``y_in = y_{j+1}`` is the vapour entering the stage from below.
    The solver constraint becomes

        y_j = y_in + E * (K_j x_j - y_in).

    ``E = 1`` recovers the ideal equilibrium stage exactly.  The reboiler
    (no entering vapour) and the total condenser keep equilibrium; the
    Murphree model applies to the contact stages in between.

``"vaporization"`` -- vapourisation efficiency (Aspen-style)
    Scales the effective K-value:

        K_eff,j = E_v,j * K_j,   i.e.  y_j = E_v K_j x_j.

    This is what a ``K_eff = K_eq x E`` formula means; it is *not* the
    Murphree efficiency even though both default to 1.

Defaults: when no :class:`EfficiencySpec` is attached to a
:class:`~h2iso.mesh.column.ColumnSpec`, the solver uses ideal stages
(``E = 1``) and behaves exactly as before this module existed.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Literal

import numpy as np

EfficiencyMode = Literal["murphree", "vaporization"]


@dataclass
class EfficiencySpec:
    """Stage-efficiency specification attached to a column.

    Parameters
    ----------
    mode : {"murphree", "vaporization"}
        Interpretation of ``value`` (see module docstring).
    value : float, ndarray, dict or None
        Efficiency value(s); ``None`` is treated as 1.0 everywhere.
        Accepted forms:

        * scalar ``float`` -> applied to every stage and species;
        * ``ndarray`` of shape ``(N,)`` -> per stage (all species);
        * ``ndarray`` of shape ``(N, Nc)`` -> per stage and species;
        * ``dict`` mapping ``(stage, species)`` -> value, where **stage is
          1-indexed from the top** (condenser = 1, matching
          ``ColumnSpec.feed_stage``) and **species is the canonical index**
          (see ``h2iso.species.species_index``).  Unspecified pairs default
          to 1.0.

    All values must lie in ``(0, 1]``.
    """

    mode: EfficiencyMode = "murphree"
    value: float | np.ndarray | dict | None = 1.0

    def __post_init__(self) -> None:
        if self.mode not in ("murphree", "vaporization"):
            raise ValueError(
                f"efficiency mode must be 'murphree' or 'vaporization'; got {self.mode!r}"
            )

    def to_matrix(self, n_stages: int, n_species: int) -> np.ndarray:
        """Expand ``value`` to an ``(n_stages, n_species)`` float array."""
        value = self.value
        if value is None:
            out = np.ones((n_stages, n_species))
        elif isinstance(value, dict):
            out = np.ones((n_stages, n_species))
            for (stage, species), eff in value.items():
                if not (1 <= stage <= n_stages):
                    raise ValueError(
                        f"efficiency dict stage {stage} out of range 1..{n_stages}"
                    )
                if not (0 <= species < n_species):
                    raise ValueError(
                        f"efficiency dict species index {species} out of range "
                        f"0..{n_species - 1}"
                    )
                out[stage - 1, species] = float(eff)
        else:
            arr = np.asarray(value, dtype=float)
            if arr.ndim == 0:
                out = np.full((n_stages, n_species), float(arr))
            elif arr.shape == (n_stages,):
                out = np.repeat(arr[:, None], n_species, axis=1)
            elif arr.shape == (n_stages, n_species):
                out = arr.copy()
            else:
                raise ValueError(
                    "efficiency array must be scalar, (N,) or (N, Nc); "
                    f"got shape {arr.shape} for N={n_stages}, Nc={n_species}"
                )

        if np.any(out <= 0.0):
            raise ValueError("efficiency values must be > 0")
        if np.any(out > 1.0):
            warnings.warn(
                "efficiency values > 1 are physically unusual (E > 1 means the "
                "leaving vapour overshoots equilibrium); continuing anyway",
                UserWarning,
                stacklevel=2,
            )
        return out


# ----------------------------------------------------------------------
# scalar helpers (usable independently of the solver)
# ----------------------------------------------------------------------


def murphree_vapor_y_out(y_in: float, y_eq: float, efficiency: float) -> float:
    """Vapour leaving a stage under the Murphree vapour-efficiency model.

    ``y_out = y_in + E * (y_eq - y_in)``.
    """
    return y_in + efficiency * (y_eq - y_in)


def murphree_efficiency(
    y_in: float | np.ndarray,
    y_out: float | np.ndarray,
    y_eq: float | np.ndarray,
) -> float | np.ndarray:
    """Realised Murphree vapour efficiency from compositions (diagnostic).

    ``E = (y_out - y_in) / (y_eq - y_in)``.  Returns 1.0 where the
    denominator vanishes (already at equilibrium, or no change possible).
    """
    y_in = np.asarray(y_in, dtype=float)
    y_out = np.asarray(y_out, dtype=float)
    y_eq = np.asarray(y_eq, dtype=float)
    denom = y_eq - y_in
    with np.errstate(divide="ignore", invalid="ignore"):
        eff = np.where(np.abs(denom) > 1e-30, (y_out - y_in) / denom, 1.0)
    if eff.ndim == 0:
        return float(eff)
    return eff


def k_effective(k_eq: float | np.ndarray, efficiency: float | np.ndarray):
    """Vapourisation-efficiency-scaled K-value: ``K_eff = E_v * K_eq``."""
    return np.asarray(efficiency, dtype=float) * np.asarray(k_eq, dtype=float)
