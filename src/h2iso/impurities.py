"""Impurity species (CO / CH4 / N2 / He-3 / He-4) -- impurity extension.

First increment of the impurity extension: registry, vapour pressure,
K-value rules and the phase-behaviour semantics needed before the solver
core can be extended from 6 to 11 components.

Physics rules (documented; sources in the A1 survey report and in
``data/parameters/impurity_data.json``):

* **CO / CH4 / N2** freeze out at ISS temperatures (triple points
  68.16 / 90.69 / 63.15 K against the 19-30 K operating window).
  :func:`pvap_impurity` raises :class:`SolidPhaseError` below the triple
  point instead of extrapolating the liquid correlation into a region
  where it has no physical meaning.  (At trace level the real question is
  solubility -- ~0.2-0.3 ppm for N2 in liquid hydrogen at 20 K -- and
  freeze-out/plugging; see the A2 survey.)
* **He-3 / He-4** have no low-pressure solid phase and critical
  temperatures (3.32 / 5.20 K) far below the operating window: they are
  supercritical, non-condensable gases and are modelled as ``K = inf``
  (never condensing).

Registry conventions
--------------------
:data:`IMPURITY_ORDER` (5 names, ``He3``/``He4`` spellings), and
:data:`ALL_SPECIES_ORDER` = the 6 hydrogen isotopologues followed by the
5 impurities (11 components; index order is API-stable).  The historical
6-species API is untouched.
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass

from h2iso._data import data_path
from h2iso.species import SPECIES_ORDER

IMPURITY_ORDER = ["CO", "CH4", "N2", "He3", "He4"]
N_IMPURITIES = 5
ALL_SPECIES_ORDER = [*SPECIES_ORDER, *IMPURITY_ORDER]
N_ALL_SPECIES = len(ALL_SPECIES_ORDER)


class SolidPhaseError(ValueError):
    """Liquid-vapour property requested below the species' triple point.

    For CO / CH4 / N2 in the ISS window this is the *expected* outcome;
    callers should treat such components as frozen-out (deposited) rather
    than continuing with an extrapolated vapour pressure.
    """


_DATA: dict | None = None


def load_impurity_data() -> dict:
    """Load (and cache) the impurity parameter file."""
    global _DATA
    if _DATA is None:
        with data_path("parameters", "impurity_data.json") as path:
            with open(path, encoding="utf-8") as f:
                _DATA = json.load(f)
    return _DATA


def impurity(species: str) -> dict:
    """Return the data block for an impurity species name."""
    data = load_impurity_data()["species"]
    if species not in data:
        raise KeyError(
            f"unknown impurity {species!r}; expected one of {IMPURITY_ORDER}"
        )
    return data[species]


def species_index_all(name: str) -> int:
    """Index within :data:`ALL_SPECIES_ORDER` (11-component convention)."""
    return ALL_SPECIES_ORDER.index(name)


def triple_point_T(species: str) -> float | None:
    """Triple-point temperature [K]; ``None`` when no low-pressure solid exists."""
    return impurity(species)["T_tp"]


def has_solid_phase(species: str) -> bool:
    """Whether the species has a low-pressure solid phase."""
    return bool(impurity(species)["has_solid_phase"])


def is_non_condensable(T: float, species: str) -> bool:
    """True when the species cannot condense at temperature ``T``.

    Supercritical above the critical temperature; also covers the helium
    isotopes in the ISS window (T_c = 3.32 / 5.20 K).
    """
    return T > float(impurity(species)["T_c"])


def pvap_impurity(T: float, species: str) -> float:
    """Saturation pressure of an impurity [Pa].

    Uses the PLXANT (DIPPR-101) fit or the EPT-76 equation from the data
    file.  Raises :class:`SolidPhaseError` below the triple point for
    species with a low-pressure solid phase; warns (but computes) when
    ``T`` lies outside the fitted/validated range above the triple point.
    """
    if T <= 0:
        raise ValueError(f"temperature must be > 0 K; got {T}")
    data = impurity(species)
    t_tp = data["T_tp"]
    if data["has_solid_phase"] and t_tp is not None and T < t_tp:
        raise SolidPhaseError(
            f"{species} is solid below its triple point ({t_tp} K); "
            f"requested T = {T} K. Liquid vapour pressure is not defined. "
            "Treat the component as frozen out (see the impurity-property note)."
        )
    pv = data["pvap"]
    lo, hi = pv["validity_K"]
    if not (lo <= T <= hi):
        warnings.warn(
            f"{species} vapour-pressure correlation is validated for "
            f"{lo}-{hi} K; T = {T} K is an extrapolation",
            UserWarning,
            stacklevel=2,
        )
    params = pv["params"]
    model = pv["model"]
    if model == "plxant":
        ln_p = (
            params["A"]
            + params["B"] / T
            + params["C"] * math.log(T)
            + params["D"] * T ** params["E"]
        )
        return math.exp(ln_p)
    if model == "antoine":
        return math.exp(params["A"] - params["B"] / (T + params["C"]))
    if model == "ept76":
        ln_p = (
            params["a_m1"] / T
            + params["a0"]
            + params["a1"] * T
            + params["a2"] * T**2
            + params["a3"] * T**3
            + params["a4"] * T**4
            + params["b"] * math.log(T)
        )
        return math.exp(ln_p)
    raise ValueError(f"unknown pvap model {model!r} for {species}")


def kvalue_impurity(T: float, P: float, species: str) -> float:
    """K-value of an impurity: ``K = pvap/P``; ``inf`` when non-condensable.

    Raises :class:`SolidPhaseError` for frozen-out species (CO/CH4/N2
    below their triple points).
    """
    if P <= 0:
        raise ValueError(f"pressure must be > 0 Pa; got {P}")
    if is_non_condensable(T, species):
        return math.inf
    return pvap_impurity(T, species) / P


# ----------------------------------------------------------------------
# feed-level impurity checks (A.2 process-question thresholds, in code)
# ----------------------------------------------------------------------

# Thresholds from the A.2 survey (sources in the A1/A2 reports):
#
# * helium: TSTA experience and JAERI-M 93-145 -- a 1 % He feed can still
#   be handled (larger condenser required), 5 % makes column pressure and
#   condenser duty roughly double (unacceptable), and helium should be
#   removed before the cascade above ~1 %;
# * ITER TEP -> ISS interface specification: total impurities < 1 ppm;
# * JET DTE1 measured a real deuterium-tritium feed at ~3.7 % total
#   impurities (He 1.61 %, N2 0.25 %, CD4 0.394 %, CO/CO2 0.039 %, water
#   1.2 %) -- i.e. real machine exhausts are far dirtier than the
#   interface spec, so front-end purification is mandatory, not optional.
DEFAULT_FEED_LIMITS = {
    "he_caution": 0.01,  # He mole fraction of the total feed
    "he_unacceptable": 0.05,
    "interface_total_ppm": 1.0,  # ITER TEP -> ISS interface spec
    "jet_dte1_total": 0.037,  # measured JET DTE1 feed, context only
}


@dataclass
class FeedAlert:
    """A feed-composition flag raised by :func:`check_feed_impurities`.

    Attributes
    ----------
    level : {"info", "warning", "critical"}
    code : str
        Stable identifier (``HE_CAUTION``, ``HE_UNACCEPTABLE``,
        ``INTERFACE_SPEC_EXCEEDED``, ``NO_IMPURITIES``).
    message : str
        Human-readable explanation with the governing source.
    """

    level: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


def _require_non_negative_finite(value: float, name: str) -> float:
    """Reject ``NaN`` / ``+-inf`` / negative impurity quantities.

    Impurity mole fractions and molar flows are physical, non-negative and
    finite; a non-finite entry silently poisons every downstream balance
    (sums become ``nan``, threshold comparisons turn False). ``0.0`` stays
    legal -- it is a vacuous but well-defined entry.
    """
    v = float(value)
    if not math.isfinite(v) or v < 0.0:
        raise ValueError(f"{name} must be a finite non-negative float; got {value!r}")
    return v


def check_feed_impurities(
    impurities: dict,
    *,
    limits: dict | None = None,
) -> list[FeedAlert]:
    """Check a feed's impurity levels against the A.2 process thresholds.

    Parameters
    ----------
    impurities : dict
        ``{species: mole_fraction}`` of the *total* feed (the same
        convention as :func:`column_impurity_disposition`).
    limits : dict, optional
        Override individual entries of :data:`DEFAULT_FEED_LIMITS`.

    Returns
    -------
    list[FeedAlert]
        Empty for a clean feed.  Helium thresholds are checked against the
        He-3 + He-4 sum; the interface specification against the total of
        all impurities present.
    """
    lim = dict(DEFAULT_FEED_LIMITS)
    if limits:
        lim.update(limits)
    unknown = sorted(set(impurities) - set(IMPURITY_ORDER))
    if unknown:
        raise KeyError(f"{unknown} are not impurity species; expected {IMPURITY_ORDER}")

    for sp, frac in impurities.items():
        _require_non_negative_finite(frac, f"impurity fraction {sp!r}")

    alerts: list[FeedAlert] = []
    total = sum(v for v in impurities.values() if v > 0)
    he = sum(v for sp, v in impurities.items() if sp in ("He3", "He4") and v > 0)

    if he >= lim["he_unacceptable"]:
        alerts.append(
            FeedAlert(
                "critical",
                "HE_UNACCEPTABLE",
                f"Feed contains {he:.2%} helium (>= {lim['he_unacceptable']:.0%}): "
                "column pressure and condenser duty roughly double. Remove He "
                "before the cascade (JAERI-M 93-145 / TSTA experience).",
            )
        )
    elif he >= lim["he_caution"]:
        alerts.append(
            FeedAlert(
                "warning",
                "HE_CAUTION",
                f"Feed contains {he:.2%} helium (>= {lim['he_caution']:.0%}): "
                "still operable but requires an oversized condenser, and the "
                "helium should be removed upstream of the cascade "
                "(JAERI-M 93-145).",
            )
        )

    if total * 1e6 > lim["interface_total_ppm"]:
        alerts.append(
            FeedAlert(
                "info",
                "INTERFACE_SPEC_EXCEEDED",
                f"Total impurities {total * 1e6:.3g} ppm exceed the ITER "
                f"TEP->ISS interface specification ({lim['interface_total_ppm']:.0f} ppm); "
                "front-end purification is required. For context, the JET DTE1 "
                f"feed measured ~{lim['jet_dte1_total']:.1%} total impurities.",
            )
        )

    if not impurities or total <= 0:
        alerts.append(
            FeedAlert(
                "info", "NO_IMPURITIES", "Feed is free of the tracked impurities."
            )
        )
    return alerts


# ----------------------------------------------------------------------
# column-level impurity disposition
# ----------------------------------------------------------------------

# Dissolved-trace caps in liquid hydrogen at ~20 K [mol fraction].
# Only N2 has a published value in the impurity literature (~0.2-0.3 ppm solubility
# in liquid hydrogen at 20 K; Barwood et al. 2025 / Campestrini et al.
# 2023, see A1/A2 reports).  CO and CH4 solubilities are a documented
# literature gap; 0.0 is a conservative default (fully frozen).
DEFAULT_SOLUBILITY_PPM = {"CO": 0.0, "CH4": 0.0, "N2": 0.3, "He3": None, "He4": None}


@dataclass
class ImpurityDisposition:
    """Where each impurity goes in a column at given operating temperatures.

    Attributes
    ----------
    species : str
    status : {"to_top", "frozen_out", "mixed"}
    feed_mol_h : float
        Impurity molar flow in the feed.
    to_top_mol_h : float
        Flow leaving with the top (distillate) product.  He isotopes leave
        entirely with the top; frozen species do **not** reach the top.
    dissolved_mol_h : float
        Dissolved trace carried by the **liquid** stream (exits with the
        bottom product, not the top).  Only applies to frozen-out species,
        capped by the solubility allowance.
    frozen_mol_h : float
        Flow expected to freeze out (deposit) somewhere in the cold column.
    basis : str
        Human-readable justification (K = inf / T < T_tp / solubility cap).
    """

    species: str
    status: str
    feed_mol_h: float
    to_top_mol_h: float
    dissolved_mol_h: float
    frozen_mol_h: float
    basis: str

    def to_dict(self) -> dict:
        return {
            "species": self.species,
            "status": self.status,
            "feed_mol_h": float(self.feed_mol_h),
            "to_top_mol_h": float(self.to_top_mol_h),
            "dissolved_mol_h": float(self.dissolved_mol_h),
            "frozen_mol_h": float(self.frozen_mol_h),
            "basis": self.basis,
        }


def classify_species(species: str, T_min: float, T_max: float) -> tuple[str, str]:
    """Classify an impurity over an operating temperature window.

    Returns ``(status, basis)`` with status one of ``"to_top"``
    (non-condensable in the whole window), ``"frozen_out"`` (below the
    triple point somewhere in the window, i.e. deposits) or
    ``"vle_active"`` (liquid-vapour equilibrium meaningful over the whole
    window -- generic support; not the ISS case at 19-30 K).
    """
    if T_min <= 0 or T_max < T_min:
        raise ValueError(f"invalid temperature window [{T_min}, {T_max}] K")
    data = impurity(species)
    t_c = float(data["T_c"])

    # Above the critical temperature there is no liquid phase at all:
    # the species cannot condense anywhere in the window.
    if T_min > t_c:
        return "to_top", f"T_min = {T_min} K > T_c = {t_c} K: supercritical (K = inf)"

    t_tp = data["T_tp"]
    if data["has_solid_phase"] and t_tp is not None and T_min < t_tp:
        return "frozen_out", (
            f"T_tp = {t_tp} K above window minimum {T_min} K: solid phase "
            "must form (deposit); liquid VLE not defined there"
        )
    return "vle_active", "liquid-vapour equilibrium meaningful in the window"


def column_impurity_disposition(
    feed_composition: dict,
    feed_flow_mol_h: float,
    T_min: float,
    T_max: float,
    *,
    liquid_flow_mol_h: float | None = None,
    solubility_ppm: dict | None = None,
) -> list[ImpurityDisposition]:
    """Compute the fate of each impurity for a column operating window.

    Parameters
    ----------
    feed_composition : dict
        ``{impurity: mole_fraction}`` (fractions of the *whole* feed,
        including the hydrogen isotopes).
    feed_flow_mol_h : float
        Total feed molar flow [mol/h].
    T_min, T_max : float
        Coldest and warmest operating temperature of the column [K]
        (typically the condenser and reboiler temperatures).
    liquid_flow_mol_h : float, optional
        Liquid flow the dissolved trace would be carried by (e.g. the
        bottom product).  Defaults to ``feed_flow_mol_h``.
    solubility_ppm : dict, optional
        Dissolved-trace cap per species [ppm of liquid]; defaults to
        :data:`DEFAULT_SOLUBILITY_PPM` (N2 only; CO/CH4 = 0 is a
        documented conservative choice).

    Returns
    -------
    list[ImpurityDisposition]
        One entry per impurity present (fraction > 0) in the feed.

    Notes
    -----
    Frozen species trigger a :class:`UserWarning` (plugging/deposition
    risk) -- callers should surface this to the user rather than proceed
    silently.  This layer implements the *corrected* acceptance semantics
    of the declared demonstration basis (the original "99 % to the top vent" claim
    holds only for the helium isotopes; see the impurity disposition documentation).
    """
    if feed_flow_mol_h <= 0:
        raise ValueError("feed_flow_mol_h must be > 0")
    _require_non_negative_finite(feed_flow_mol_h, "feed_flow_mol_h")
    if liquid_flow_mol_h is not None:
        _require_non_negative_finite(liquid_flow_mol_h, "liquid_flow_mol_h")
    caps = dict(DEFAULT_SOLUBILITY_PPM)
    if solubility_ppm:
        caps.update(solubility_ppm)
    carrier = feed_flow_mol_h if liquid_flow_mol_h is None else liquid_flow_mol_h

    out = []
    for sp, frac in feed_composition.items():
        _require_non_negative_finite(frac, f"feed impurity fraction {sp!r}")
        if frac <= 0:
            continue
        if sp not in IMPURITY_ORDER:
            raise KeyError(
                f"{sp!r} is not an impurity species; expected {IMPURITY_ORDER}"
            )
        flow = frac * feed_flow_mol_h
        status, basis = classify_species(sp, T_min, T_max)
        if status == "to_top":
            out.append(ImpurityDisposition(sp, "to_top", flow, flow, 0.0, 0.0, basis))
            continue
        if status == "frozen_out":
            cap_ppm = caps.get(sp)
            dissolved = 0.0
            if cap_ppm:
                dissolved = min(flow, cap_ppm * 1e-6 * carrier)
            frozen = flow - dissolved
            basis_full = basis + (
                f"; dissolved trace {dissolved:.3g} mol/h stays in the liquid "
                f"(cap {cap_ppm} ppm of liquid)"
                if dissolved > 0
                else "; fully frozen out (no dissolved-trace allowance)"
            )
            warnings.warn(
                f"Impurity {sp}: {frozen:.6g} mol/h is expected to FREEZE OUT "
                f"in the column ({basis}). Deposition/plugging risk; the "
                "phase-equilibrium model does not apply to this component.",
                UserWarning,
                stacklevel=2,
            )
            out.append(
                ImpurityDisposition(
                    sp, "frozen_out", flow, 0.0, dissolved, frozen, basis_full
                )
            )
            continue
        # vle_active (generic future case; not expected for the ISS window)
        out.append(
            ImpurityDisposition(
                sp, "mixed", flow, 0.0, 0.0, 0.0, basis + "; share not modelled here"
            )
        )
    return out


def dilute_top_product(
    x_top: dict, impurity_flows_to_top_mol_h: dict, distillate_flow_mol_h: float
) -> tuple[dict, float]:
    """Dilute a top-product composition by the impurities leaving with it.

    Parameters
    ----------
    x_top : dict
        Baseline top-product mole fractions (e.g. ``{"D2": 0.999966,
        "DT": 0.000034}``), summing to 1.
    impurity_flows_to_top_mol_h : dict
        ``{impurity: mol/h}`` leaving with the top product.
    distillate_flow_mol_h : float
        Baseline distillate molar flow [mol/h] (without impurities).

    Returns
    -------
    (x_diluted, relative_purity_change) : (dict, float)
        Diluted composition over all species present, and the relative
        change of the dominant (baseline-main) fraction.
    """
    if distillate_flow_mol_h <= 0:
        raise ValueError("distillate_flow_mol_h must be > 0")
    imp_total = sum(impurity_flows_to_top_mol_h.values())
    total = distillate_flow_mol_h + imp_total
    x_dil = {}
    for sp, frac in x_top.items():
        x_dil[sp] = frac * distillate_flow_mol_h / total
    for sp, flow in impurity_flows_to_top_mol_h.items():
        x_dil[sp] = flow / total
    main = max(x_top, key=x_top.get)
    rel_change = (x_top[main] - x_dil[main]) / x_top[main] if x_top[main] > 0 else 0.0
    return x_dil, rel_change
