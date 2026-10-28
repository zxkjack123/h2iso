"""Flowsheet-level impurity routing (flowsheet tracer layer).

The single-column disposition layer (:mod:`h2iso.impurities`) answers
*where each impurity goes inside one column*.  This module answers the
follow-up question of the ISS design work: **where does an impurity leave
a multi-column cascade (which terminus: purge branch / declared product
end / undeclared terminal end), and where does it deposit?**

Model -- tracer / post-processing semantics
-------------------------------------------
Impurities are treated as tracers on a *converged* 6-isotope flowsheet
solution:

* UNVERIFIED ASSUMPTION: the 6-isotope core is solved normally and this
  impurity layer does not feed back into temperature, flow or composition
  profiles.  That ppm-to-percent impurity amounts cannot perturb the core
  is a modelling assumption, not a verified result;
* each injection is classified with the full operating window of its
  entry column (min/max of the solved ``T_profile``) and then routed
  along the flowsheet graph:

  - non-condensable species (K = inf, i.e. the helium isotopes) leave
    with the **top** product and follow the top stream -- through any
    downstream column (re-classified with that column's window) -- until
    a terminal stream;
  - frozen-out species deposit in the column where they enter; their
    dissolved trace is reported as leaving with that column's bottoms
    liquid;
* multi-destination streams use ``config.splitter`` ratios when
  configured, otherwise every branch receives the full flow -- matching
  the sequential-modular solver's own ``_apply_split`` behaviour.

Limitations (documented, not silent)
------------------------------------
* The ppm-level dissolved trace is reported at the bottoms stream of its
  entry column and is not traced further downstream;
* a walk that re-enters a column it has already visited is reported as
  ``recirculating`` instead of looping.

Injection convention
--------------------
:func:`route_impurities` takes **absolute molar flows** keyed by the
column the impurity enters::

    {"CD2": {"He4": 0.4018, "CO": 0.8036, "N2": 0.4018}}   # mol/h

(The single-column API instead takes mole fractions of a feed; at
flowsheet level the entry point is a column, and absolute flows are
unambiguous there.)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from h2iso.impurities import (
    IMPURITY_ORDER,
    _require_non_negative_finite,
    classify_species,
    column_impurity_disposition,
)
from h2iso.purge import PurgeDesign, design_purge

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module casadi-free
    from h2iso.flowsheet.schema import FlowsheetConfig


@dataclass
class ImpurityRoute:
    """The fate of one impurity injection along the flowsheet graph.

    Attributes
    ----------
    species : str
    entry_column : str
        Column the impurity was injected into.
    status : {"vent", "product", "frozen", "dissolved", "vle_active", "recirculating"}
        ``vent``  -- reached a **terminal stream** (a product end, or an end
        the flowsheet does not connect or declare).  **LEGACY NAME -- it does
        NOT mean the impurity entered a vent**; read :attr:`terminal_kind`
        instead.  A real condenser purge branch is ``purge``.
        ``product`` -- left with a bottoms/terminal stream (legacy value);
        ``frozen`` -- deposited in ``destination`` (a column);
        ``dissolved`` -- ppm trace leaving with a bottoms liquid;
        ``recirculating`` -- re-entered an already-visited column;
        ``vle_active`` -- condensable everywhere (not an ISS case).
    destination : str
        Terminal stream name, column name (deposition) or bottoms stream.
    path : list[str]
        Units/streams visited, e.g. ``["CD2", "CD2_top", "CD1", "CD1_top"]``.
    flow_mol_h : float
    basis : str
        Human-readable justification (K = inf / T < T_tp / splitter note).
    terminal_kind : {"purge_branch", "declared_product_end", \
"undeclared_terminal_end", None}
        Unambiguous, mutually exclusive classification of the terminus
        (three states, exactly one applies when the impurity leaves the
        flowsheet):

        * ``purge_branch`` -- routed into a real condenser purge branch;
        * ``declared_product_end`` -- reached a stream declared in
          ``config.products``;
        * ``undeclared_terminal_end`` -- reached a leaf stream that the
          flowsheet neither connects nor declares.

        ``None`` for routes that do not terminate at a stream (``frozen``,
        ``dissolved``, ``recirculating``, ``vle_active``).
    """

    species: str
    entry_column: str
    status: str
    destination: str
    path: list[str]
    flow_mol_h: float
    basis: str
    terminal_kind: str | None = None

    @property
    def exits_via_terminal_stream(self) -> bool:
        """True for both terminal-stream kinds (product end / undeclared end).

        This is **False** for a real condenser purge branch -- use
        :attr:`enters_purge_branch` for that question.
        """
        return self.terminal_kind in (
            "declared_product_end",
            "undeclared_terminal_end",
        )

    @property
    def enters_purge_branch(self) -> bool:
        """True only when the route ends in a real condenser purge branch."""
        return self.terminal_kind == "purge_branch"

    @property
    def enters_vent(self) -> bool:
        """DEPRECATED / MISLEADING NAME -- do not use this to answer
        "did the impurity enter a vent?".

        The historical body (``status in ("vent", "product")``) is kept
        verbatim for backward compatibility, but it is **True for a plain
        product terminus** and **False for a real condenser purge branch**.
        It therefore cannot distinguish a product end from a purge branch.
        Use :attr:`exits_via_terminal_stream` or :attr:`enters_purge_branch`
        instead.
        """
        return self.status in ("vent", "product")

    def to_dict(self) -> dict:
        return {
            "species": self.species,
            "entry_column": self.entry_column,
            "status": self.status,
            "destination": self.destination,
            "path": list(self.path),
            "flow_mol_h": float(self.flow_mol_h),
            "basis": self.basis,
            "terminal_kind": self.terminal_kind,
        }


@dataclass
class FlowsheetImpurityReport:
    """Aggregated result of :func:`route_impurities`."""

    routes: list[ImpurityRoute] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: V1.2 purge branches, keyed by column (empty in the V1.1 scheme)
    purge_designs: dict[str, PurgeDesign] = field(default_factory=dict)

    def by_destination(self) -> dict[str, dict[str, float]]:
        """``{destination: {species: mol/h}}`` -- where impurities end up."""
        out: dict[str, dict[str, float]] = {}
        for r in self.routes:
            out.setdefault(r.destination, {})
            out[r.destination][r.species] = (
                out[r.destination].get(r.species, 0.0) + r.flow_mol_h
            )
        return out

    def by_status(self) -> dict[str, dict[str, float]]:
        """``{status: {species: mol/h}}`` -- vent / frozen / dissolved totals."""
        out: dict[str, dict[str, float]] = {}
        for r in self.routes:
            out.setdefault(r.status, {})
            out[r.status][r.species] = out[r.status].get(r.species, 0.0) + r.flow_mol_h
        return out

    def frozen_columns(self) -> dict[str, dict[str, float]]:
        """``{column: {species: mol/h}}`` -- deposition locations."""
        out: dict[str, dict[str, float]] = {}
        for r in self.routes:
            if r.status != "frozen":
                continue
            out.setdefault(r.destination, {})
            out[r.destination][r.species] = (
                out[r.destination].get(r.species, 0.0) + r.flow_mol_h
            )
        return out

    def to_dict(self) -> dict:
        return {
            "routes": [r.to_dict() for r in self.routes],
            "by_destination": self.by_destination(),
            "by_status": self.by_status(),
            "purge_designs": {k: v.to_dict() for k, v in self.purge_designs.items()},
            "warnings": list(self.warnings),
        }


def _connection_map(config) -> dict[str, list[str]]:
    """``{from_unit: [to_unit, ...]}`` from the configured topology."""
    out: dict[str, list[str]] = {}
    for conn in config.connections:
        out.setdefault(conn.from_unit, []).append(conn.to_unit)
    return out


def _terminal_kind(config, stream: str) -> str:
    """Classify a terminal stream as a declared product end or an open end.

    ``status == "vent"`` covers both; this is what tells them apart.
    """
    products = getattr(config, "products", None) or {}
    return "declared_product_end" if stream in products else "undeclared_terminal_end"


def _column_windows(result) -> dict[str, tuple[float, float]]:
    """``{column: (T_min, T_max)}`` from the solved temperature profiles."""
    windows: dict[str, tuple[float, float]] = {}
    for name, col_result in result.column_results.items():
        t_profile = col_result.T_profile
        windows[name] = (float(min(t_profile)), float(max(t_profile)))
    return windows


def _bottom_liquid_flow(result, column: str) -> float | None:
    """Liquid flow leaving the bottoms of ``column`` [mol/h], if available."""
    col_result = result.column_results.get(column)
    if col_result is None or col_result.L_profile is None:
        return None
    return float(col_result.L_profile[-1])


def _distillate_flow(result, column: str) -> float | None:
    """Distillate flow of ``column`` [mol/h], if available.

    Prefers the solved flowsheet stream (``{column}_distillate``); falls
    back to the interstage liquid difference for bare column results.
    Returns ``None`` when neither is available (the purge design then
    simply omits the product-relative loss).
    """
    streams = getattr(result, "streams", None) or {}
    stream = streams.get(f"{column}_distillate")
    if stream is not None:
        return float(stream.flow)
    col_result = result.column_results.get(column)
    if col_result is None or col_result.L_profile is None:
        return None
    L = col_result.L_profile
    if len(L) < 2:
        return None
    return float(L[0] - L[1])


def route_impurities(
    config: FlowsheetConfig,
    result,
    injections: dict[str, dict[str, float]],
    *,
    solubility_ppm: dict | None = None,
    purges: dict | None = None,
) -> FlowsheetImpurityReport:
    """Route impurity injections through a converged flowsheet solution.

    Parameters
    ----------
    config : FlowsheetConfig
        The topology the result was solved from.
    result : FlowsheetResult
        A converged sequential-modular result (only ``column_results``,
        their ``T_profile``/``L_profile`` and the topology are used -- the
        object is duck-typed, so any compatible result works).
    injections : dict
        ``{column_name: {species: mol_per_h}}`` -- see the module
        docstring for the convention.
    solubility_ppm : dict, optional
        Dissolved-trace caps, forwarded to
        :func:`h2iso.impurities.column_impurity_disposition`.
    purges : dict, optional
        ``{column_name: PurgeSpec}`` -- the **V1.2 scheme**: a
        non-condensable purge branch in that column's condenser head
        space.  Helium reaching a purged column leaves through
        ``f"{column}_purge"`` instead of the top product, and the
        co-vented condensable (D2/DT/T2) loss is designed with
        :func:`h2iso.purge.design_purge` and returned in
        ``report.purge_designs``.  The vent pressure defaults to the
        column's top pressure from ``config``.

    Returns
    -------
    FlowsheetImpurityReport

    Warns
    -----
    UserWarning
        Anything that froze (deposition risk) -- forwarded from the
        single-column disposition layer, so callers cannot miss it.  A
        purge design that would freeze in the vent point is flagged in
        ``PurgeDesign.feasible`` (no warning: it is a design outcome).
    """
    windows = _column_windows(result)
    outgoing = _connection_map(config)
    known_units = {c.name for c in config.columns} | {
        e.name for e in config.equilibrators
    }
    purges = dict(purges or {})
    top_pressures = {c.name: c.pressure_top_Pa for c in config.columns}
    arrivals: dict[str, float] = {}  # column -> helium flow arriving [mol/h]
    report = FlowsheetImpurityReport()

    for column, composition in injections.items():
        if column not in windows:
            raise KeyError(
                f"injection column {column!r} has no solved result; "
                f"available: {sorted(windows)}"
            )
        flows = {sp: float(q) for sp, q in composition.items() if q}
        if not flows:
            continue
        bad = sorted(set(flows) - set(IMPURITY_ORDER))
        if bad:
            raise KeyError(f"{bad} are not impurity species; expected {IMPURITY_ORDER}")

        # Injected impurity flows are non-negative finite molar flows; the
        # vector is then normalised by its own total, so a non-finite or
        # negative entry (or a total of zero from mixed signs) would make the
        # scaling meaningless.
        for sp, q in flows.items():
            _require_non_negative_finite(q, f"injected {sp} flow [mol/h]")

        total = sum(flows.values())
        if total <= 0:
            raise ValueError(
                f"injected impurity flows must sum to a positive total; got {total!r}"
            )
        fractions = {sp: q / total for sp, q in flows.items()}
        t_min, t_max = windows[column]
        carrier = _bottom_liquid_flow(result, column)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            disposition = column_impurity_disposition(
                fractions,
                total,
                t_min,
                t_max,
                liquid_flow_mol_h=carrier,
                solubility_ppm=solubility_ppm,
            )
        for w in caught:
            report.warnings.append(str(w.message))
            warnings.warn(str(w.message), UserWarning, stacklevel=2)

        for entry in disposition:
            if entry.status == "to_top":
                if column in purges:
                    # the non-condensable never leaves with the top product
                    arrivals[column] = arrivals.get(column, 0.0) + entry.to_top_mol_h
                    report.routes.append(
                        ImpurityRoute(
                            entry.species,
                            column,
                            "purge",
                            f"{column}_purge",
                            [column, f"{column}_purge"],
                            entry.to_top_mol_h,
                            entry.basis + "; diverted to the condenser purge branch "
                            "(V1.2) instead of the top product",
                            "purge_branch",
                        )
                    )
                    continue
                report.routes.extend(
                    _walk_vapor(
                        outgoing,
                        windows,
                        known_units,
                        config,
                        column,
                        entry.species,
                        entry.to_top_mol_h,
                        path=[column, f"{column}_top"],
                        visited={column},
                        basis=entry.basis,
                        purges=purges,
                        arrivals=arrivals,
                    )
                )
            elif entry.status == "frozen_out":
                if entry.frozen_mol_h > 0:
                    report.routes.append(
                        ImpurityRoute(
                            entry.species,
                            column,
                            "frozen",
                            column,
                            [column],
                            entry.frozen_mol_h,
                            entry.basis,
                        )
                    )
                if entry.dissolved_mol_h > 0:
                    report.routes.append(
                        ImpurityRoute(
                            entry.species,
                            column,
                            "dissolved",
                            f"{column}_bottom",
                            [column, f"{column}_bottom"],
                            entry.dissolved_mol_h,
                            entry.basis,
                        )
                    )
            else:  # vle_active / mixed -- generic future case
                report.routes.append(
                    ImpurityRoute(
                        entry.species,
                        column,
                        "vle_active",
                        column,
                        [column],
                        entry.feed_mol_h,
                        entry.basis,
                    )
                )

    # V1.2: design one purge branch per column that actually receives
    # helium (the arrival flows were recorded during the walk, so a purge
    # downstream of another purge is never designed for phantom helium).
    for column, he_flow in arrivals.items():
        if column not in purges:
            continue
        spec = purges[column]
        report.purge_designs[column] = design_purge(
            result.column_results[column],
            he_flow,
            spec,
            pressure_Pa=top_pressures.get(column),
            product_flow_mol_h=_distillate_flow(result, column),
        )
    return report


def _walk_vapor(
    outgoing: dict[str, list[str]],
    windows: dict[str, tuple[float, float]],
    known_units: set[str],
    config,
    from_column: str,
    species: str,
    flow: float,
    *,
    path: list[str],
    visited: set[str],
    basis: str,
    purges: dict | None = None,
    arrivals: dict[str, float] | None = None,
) -> list[ImpurityRoute]:
    """Follow a non-condensable impurity along top streams to its sink."""
    if flow <= 0:
        return []
    purges = purges or {}
    stream = path[-1]
    destinations = outgoing.get(stream, [])
    if not destinations:
        return [
            ImpurityRoute(
                species,
                from_column,
                "vent",
                stream,
                list(path),
                flow,
                basis,
                _terminal_kind(config, stream),
            )
        ]

    routes: list[ImpurityRoute] = []
    split = getattr(config, "splitter", {}) or {}
    for dest in destinations:
        ratio = 1.0
        note = basis
        if len(destinations) > 1:
            configured = split.get(stream, {}).get(dest)
            if configured is not None:
                ratio = float(configured)
                note = f"{basis}; splitter ratio {ratio:g} applied"
            else:
                note = (
                    f"{basis}; no splitter ratio configured -- full flow "
                    "carried on every branch (matches the SM solver)"
                )
        branch_flow = flow * ratio
        if branch_flow <= 0:
            continue
        if dest in windows:  # downstream column
            if arrivals is not None:
                arrivals[dest] = arrivals.get(dest, 0.0) + branch_flow
            if dest in purges:
                routes.append(
                    ImpurityRoute(
                        species,
                        from_column,
                        "purge",
                        f"{dest}_purge",
                        [*path, dest, f"{dest}_purge"],
                        branch_flow,
                        note + f"; diverted to the {dest} condenser purge branch "
                        "(V1.2) instead of the top product",
                        "purge_branch",
                    )
                )
                continue
            if dest in visited:
                routes.append(
                    ImpurityRoute(
                        species,
                        from_column,
                        "recirculating",
                        dest,
                        [*path, dest],
                        branch_flow,
                        note + "; re-enters an already-visited column "
                        "(accumulates in the recycle loop)",
                    )
                )
                continue
            status, why = classify_species(species, *windows[dest])
            if status == "to_top":
                routes.extend(
                    _walk_vapor(
                        outgoing,
                        windows,
                        known_units,
                        config,
                        from_column,
                        species,
                        branch_flow,
                        path=[*path, dest, f"{dest}_top"],
                        visited=visited | {dest},
                        basis=note + f"; non-condensable in {dest}",
                        purges=purges,
                        arrivals=arrivals,
                    )
                )
            elif status == "frozen_out":
                routes.append(
                    ImpurityRoute(
                        species,
                        from_column,
                        "frozen",
                        dest,
                        [*path, dest],
                        branch_flow,
                        note + f"; {why}",
                    )
                )
            else:
                routes.append(
                    ImpurityRoute(
                        species,
                        from_column,
                        "vle_active",
                        dest,
                        [*path, dest],
                        branch_flow,
                        note + f"; {why}",
                    )
                )
        elif dest in known_units:  # equilibrator / other pass-through unit
            routes.extend(
                _walk_vapor(
                    outgoing,
                    windows,
                    known_units,
                    config,
                    from_column,
                    species,
                    branch_flow,
                    path=[*path, dest],
                    visited=visited,
                    basis=note + f"; passes through {dest} unchanged",
                    purges=purges,
                    arrivals=arrivals,
                )
            )
        else:  # terminal stream (declared product end or undeclared end)
            routes.append(
                ImpurityRoute(
                    species,
                    from_column,
                    "vent",
                    dest,
                    [*path, dest],
                    branch_flow,
                    note,
                    _terminal_kind(config, dest),
                )
            )
    return routes
