"""Non-condensable (helium) purge branch -- the V1.2 scheme.

Background
----------
Without a dedicated vent, the helium entering a column leaves with its top
product (V1.1): in the CFEDR ISS-I cascade that means the helium ends up in
the D2-rich WDS-D product, which then needs a downstream separation step.

V1.2 adds a **purge branch** in the condenser head space of the column: a
small gas side-draw that removes the accumulated non-condensable and
returns the co-vented condensate to the column.

Physics (single equilibrium stage = thermodynamic limit)
--------------------------------------------------------
The vent gas is in equilibrium with the condensate at the vent point, at
temperature ``T_vent`` and pressure ``P``:

    y_He   = p_He / P                      (design variable)
    y_i    = K_i(T_vent, P, x_top) * x_i   (condensables, Raoult + quantum
                                            fugacity correction, as in the
                                            rest of h2iso)

so the enrichment fixes the vent temperature through

    Σ_i K_i(T_vent, P, x_top) · x_i  =  1 - y_He.

Two consequences are worth stating explicitly:

* **the condensable loss is fixed by the enrichment**, not by the number
  of stages: per mole of helium the vent carries ``(1 - y_He)/y_He`` moles
  of condensables.  With an infinitely volatile non-condensable the vapour
  leaving the last equilibrium stage is in equilibrium with the nearly
  pure condensate, so this single-stage result is the *lower bound* for
  any staged dephlegmator (real hardware loses more);
* reaching a high enrichment requires **subcooling**: ``T_vent`` falls
  below the condenser temperature, and it may not fall below the freezing
  point of the condensate -- which caps ``y_He`` (see
  :func:`max_feasible_enrichment`).  Raising the vent pressure raises
  ``T_vent`` for the same enrichment and therefore widens the window.

Freezing limit: the liquidus of a mixture is approximated by the triple
point of its **major** component (species with x_i >= 1 %); a real vent
point must stay above it with margin.

All temperatures/pressures are SI (K, Pa); flows are mol/h.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from h2iso.species import SPECIES_ORDER
from h2iso.vle.mixing import kvalue
from h2iso.vle.souers import triple_point

#: species whose mole fraction at or above this level set the freezing floor
FLOOR_X_THRESHOLD = 0.01

#: tritium atoms per molecule (used for the tritium-loss accounting)
_T_ATOMS = {"HT": 1, "DT": 1, "T2": 2}


@dataclass
class PurgeSpec:
    """Design of a non-condensable purge branch.

    Parameters
    ----------
    column : str
        Column whose condenser carries the branch.
    he_enrichment : float
        Design helium mole fraction in the vent gas ``y_He`` (0 < y < 1).
        TSTA experience: 0.18-0.27 is what a real head space reaches.
    pressure_Pa : float, optional
        Pressure at the vent point.  Defaults to the column's top pressure
        passed to :func:`design_purge`.
    margin_K : float
        Safety margin kept above the freezing floor [K].
    """

    column: str
    he_enrichment: float
    pressure_Pa: float | None = None
    margin_K: float = 0.5

    def __post_init__(self):
        if not 0.0 < self.he_enrichment < 1.0:
            raise ValueError(
                f"he_enrichment must be in (0, 1); got {self.he_enrichment}"
            )
        if self.pressure_Pa is not None and self.pressure_Pa <= 0:
            raise ValueError(f"pressure must be > 0 Pa; got {self.pressure_Pa}")
        if self.margin_K < 0:
            raise ValueError(f"margin_K must be >= 0; got {self.margin_K}")


@dataclass
class PurgeDesign:
    """Result of :func:`design_purge` for one column and enrichment."""

    column: str
    he_flow_mol_h: float
    he_enrichment: float
    pressure_Pa: float
    T_condenser_K: float
    T_vent_K: float
    subcooling_K: float
    condensable_loss_mol_h: dict[str, float] = field(default_factory=dict)
    loss_total_mol_h: float = 0.0
    tritium_loss_mol_h: float = 0.0  # mol T atoms/h
    feasible: bool = True
    limiting_species: str | None = None
    floor_K: float | None = None
    fraction_of_distillate: float | None = None
    basis: str = ""

    @property
    def loss_per_he_mol(self) -> float:
        """Condensable moles vented per mole of helium."""
        if self.he_flow_mol_h <= 0:
            return 0.0
        return self.loss_total_mol_h / self.he_flow_mol_h

    def to_dict(self) -> dict:
        return {
            "column": self.column,
            "he_flow_mol_h": self.he_flow_mol_h,
            "he_enrichment": self.he_enrichment,
            "pressure_Pa": self.pressure_Pa,
            "T_condenser_K": self.T_condenser_K,
            "T_vent_K": self.T_vent_K,
            "subcooling_K": self.subcooling_K,
            "condensable_loss_mol_h": dict(self.condensable_loss_mol_h),
            "loss_total_mol_h": self.loss_total_mol_h,
            "loss_per_he_mol": self.loss_per_he_mol,
            "tritium_loss_mol_h": self.tritium_loss_mol_h,
            "feasible": self.feasible,
            "limiting_species": self.limiting_species,
            "floor_K": self.floor_K,
            "fraction_of_distillate": self.fraction_of_distillate,
            "basis": self.basis,
        }


def _sum_y(T: float, P: float, x: np.ndarray) -> float:
    """Σ K_i(T, P, x)·x_i -- the bubble pressure of ``x`` at T, over P."""
    K = kvalue(T, P, x)
    return float(np.sum(K * x))


def _freezing_floor(x: np.ndarray) -> tuple[float, str]:
    """Freezing floor of the condensate and the species that sets it."""
    floor, who = -np.inf, None
    for i, sp in enumerate(SPECIES_ORDER):
        if x[i] >= FLOOR_X_THRESHOLD:
            t_tp, _ = triple_point(sp)
            if t_tp > floor:
                floor, who = t_tp, sp
    if who is None:  # degenerate composition -> use the largest fraction
        i = int(np.argmax(x))
        who = SPECIES_ORDER[i]
        floor, _ = triple_point(who)
    return float(floor), who


def _vent_temperature(y_he: float, P: float, x: np.ndarray, T_cond: float) -> float:
    """Solve Σ K_i(T,P,x)·x_i = 1 - y_he by bisection on [T_lo, T_cond]."""
    target = 1.0 - y_he
    T_hi = T_cond
    T_lo = max(1.0, T_cond - 20.0)
    # walk down until the residual changes sign
    f_hi = _sum_y(T_hi, P, x) - target
    for _ in range(200):
        f_lo = _sum_y(T_lo, P, x) - target
        if f_lo <= 0.0:
            break
        T_lo = max(1.0, T_lo - 2.0)
        if T_lo <= 1.0:
            raise ValueError(
                f"could not bracket the vent temperature for y_He={y_he} at "
                f"P={P:.0f} Pa (condensate barely condensable?)"
            )
    else:  # pragma: no cover - defensive
        raise ValueError("vent-temperature bracketing failed")
    if f_hi <= 0:
        raise ValueError(
            f"target Σ y = {target:.6f} is above the bubble value "
            f"{target + f_hi:.6f} at the condenser temperature"
        )
    for _ in range(200):
        T_mid = 0.5 * (T_lo + T_hi)
        if _sum_y(T_mid, P, x) - target > 0.0:
            T_hi = T_mid
        else:
            T_lo = T_mid
    return 0.5 * (T_lo + T_hi)


def design_purge(
    column_result,
    he_flow_mol_h: float,
    purge: PurgeSpec,
    *,
    pressure_Pa: float | None = None,
    product_flow_mol_h: float | None = None,
) -> PurgeDesign:
    """Design the purge branch for one column at one He enrichment.

    Parameters
    ----------
    column_result : ColumnResult
        Solved column (``x_profile[0]`` = top liquid, ``T_profile[0]`` =
        condenser temperature).
    he_flow_mol_h : float
        Helium flow reaching this column [mol/h] -- the steady-state purge
        flow, since helium does not accumulate.
    purge : PurgeSpec
    pressure_Pa : float, optional
        Vent pressure; defaults to ``purge.pressure_Pa``.  One of the two
        must be given.
    product_flow_mol_h : float, optional
        Distillate flow, to report the loss as a fraction of the product.

    Returns
    -------
    PurgeDesign
    """
    P = purge.pressure_Pa if pressure_Pa is None else pressure_Pa
    if P is None:
        raise ValueError(
            "vent pressure required (PurgeSpec.pressure_Pa or pressure_Pa)"
        )
    if he_flow_mol_h < 0:
        raise ValueError(f"he_flow_mol_h must be >= 0; got {he_flow_mol_h}")

    x = np.asarray(column_result.x_profile[0], dtype=np.float64)
    T_cond = float(column_result.T_profile[0])
    floor, floor_species = _freezing_floor(x)

    T_vent = _vent_temperature(purge.he_enrichment, P, x, T_cond)
    K = kvalue(T_vent, P, x)
    y = K * x  # condensable fraction of the vent gas
    losses = {
        sp: float(he_flow_mol_h * y[i] / purge.he_enrichment)
        for i, sp in enumerate(SPECIES_ORDER)
        if y[i] > 0
    }
    loss_total = float(sum(losses.values()))
    tritium = float(sum(_T_ATOMS.get(sp, 0) * q for sp, q in losses.items()))

    feasible = T_vent >= floor + purge.margin_K
    frac = None
    if product_flow_mol_h:
        frac = loss_total / product_flow_mol_h

    basis = (
        f"equilibrium vent at y_He = {purge.he_enrichment:.3f}: "
        f"T_vent = {T_vent:.2f} K ({T_cond - T_vent:.2f} K below the condenser), "
        f"condensable loss {loss_total / he_flow_mol_h if he_flow_mol_h else 0:.2f} "
        f"mol per mol He (= (1-y)/y, stage-count independent lower bound); "
        f"freezing floor {floor:.2f} K ({floor_species})"
    )
    if not feasible:
        basis += (
            f" -- INFEASIBLE: {T_vent:.2f} K is within {purge.margin_K:.1f} K of "
            "the floor; raise the vent pressure, lower the enrichment, or "
            "freeze-trap the non-condensable instead"
        )

    return PurgeDesign(
        column=purge.column,
        he_flow_mol_h=he_flow_mol_h,
        he_enrichment=purge.he_enrichment,
        pressure_Pa=float(P),
        T_condenser_K=T_cond,
        T_vent_K=T_vent,
        subcooling_K=T_cond - T_vent,
        condensable_loss_mol_h=losses,
        loss_total_mol_h=loss_total,
        tritium_loss_mol_h=tritium,
        feasible=feasible,
        limiting_species=floor_species,
        floor_K=floor,
        fraction_of_distillate=frac,
        basis=basis,
    )


def max_feasible_enrichment(
    column_result,
    purge: PurgeSpec,
    *,
    pressure_Pa: float | None = None,
) -> float:
    """Highest helium enrichment reachable above the freezing floor."""
    P = purge.pressure_Pa if pressure_Pa is None else pressure_Pa
    if P is None:
        raise ValueError("vent pressure required")
    x = np.asarray(column_result.x_profile[0], dtype=np.float64)
    floor, _ = _freezing_floor(x)
    T_limit = floor + purge.margin_K
    return float(1.0 - _sum_y(T_limit, P, x))


def sweep_purge(
    column_result,
    he_flow_mol_h: float,
    purge: PurgeSpec,
    enrichments: list[float] | tuple[float, ...],
    *,
    pressure_Pa: float | None = None,
    product_flow_mol_h: float | None = None,
) -> list[PurgeDesign]:
    """Run :func:`design_purge` over a list of He enrichments."""
    return [
        design_purge(
            column_result,
            he_flow_mol_h,
            PurgeSpec(purge.column, y, purge.pressure_Pa, purge.margin_K),
            pressure_Pa=pressure_Pa,
            product_flow_mol_h=product_flow_mol_h,
        )
        for y in enrichments
    ]
