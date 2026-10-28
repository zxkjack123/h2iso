# Impurities API Reference

The impurity extension treats CO / CH4 / N2 / He-3 / He-4 as a **post-processing
layer** on the 6-isotope core:
CO/CH4/N2 are solid below their triple points in the ISS window, and the helium
isotopes are supercritical non-condensables (`K = inf`) — neither belongs inside
the MESH equilibrium equations.

## Assumptions (all UNVERIFIED)

This layer is an **experimental post-processing convention**, not a physical
acceptance of impurity transport. Four assumptions are load-bearing and none of
them is verified:

1. `UNVERIFIED` — the CO/CH4 dissolved-trace cap is set to zero because no
   published solubility in liquid hydrogen was found. `0.0` means "fully
   frozen"; it is a modelling choice, not a measured value.
2. `UNVERIFIED` — `classify_species()` keys on the operating temperature window
   only. It is insensitive to impurity concentration and implements no
   solubility- or saturation-limited criterion.
3. `UNVERIFIED` — `frozen_mol_h` is an **accounting allocation** (impurity flow
   minus the dissolved-trace cap), not a solid-phase equilibrium solution. It
   does not predict deposition location, accumulation or plugging.
4. `UNVERIFIED` — the layer runs on a converged six-component MESH solution and
   does not feed back into temperature, flow or composition profiles. That the
   trace-level influence is negligible is itself unverified.

## `h2iso.impurities` — Registry, properties, disposition

### `IMPURITY_ORDER`, `ALL_SPECIES_ORDER`

```python
from h2iso.impurities import IMPURITY_ORDER, ALL_SPECIES_ORDER

IMPURITY_ORDER       # ["CO", "CH4", "N2", "He3", "He4"]
ALL_SPECIES_ORDER    # 6 isotopologues + 5 impurities (11 components)
```

### `pvap_impurity(T, species)` / `kvalue_impurity(T, P, species)`

Saturation pressure (PLXANT / He-3 EPT-76) and `K = pvap / P`.

**Raises:** `SolidPhaseError` below the triple point (CO/CH4/N2 in the ISS
window) instead of extrapolating the liquid correlation. `K = inf` for
supercritical species.

### `classify_species(species, T_min, T_max)`

Returns `(status, basis)` with status `"to_top"` (non-condensable over the whole
window), `"frozen_out"` (deposits somewhere in the window) or `"vle_active"`.

### `column_impurity_disposition(feed_composition, feed_flow_mol_h, T_min, T_max, ...)`

One `ImpurityDisposition` per impurity present, splitting the flow into
`to_top_mol_h` (leaves with the top product — helium only), `dissolved_mol_h`
(ppm trace carried by the **liquid**, i.e. the bottoms product, capped by
solubility) and `frozen_mol_h` (deposits in the column). Frozen species raise a
`UserWarning` — deposition/plugging risk must not be missed.

`frozen_mol_h` is an accounting allocation (`impurity flow - dissolved trace`),
not a solid-phase equilibrium result: it does not predict where the solid forms,
how it accumulates, or when it plugs the column (see the assumptions above).

```python
from h2iso.impurities import column_impurity_disposition

disp = column_impurity_disposition(
    {"CO": 0.01, "N2": 0.005, "He4": 0.005}, 80.357, 23.4, 24.8,
    liquid_flow_mol_h=1.69,
)
```

### `check_feed_impurities(impurities, *, limits=None)`

Feed thresholds from published impurity surveys: helium caution at 1 % and unacceptable at
5 % (JAERI-M 93-145 / TSTA experience), total impurities against the ITER
TEP→ISS interface specification (1 ppm; JET DTE1 measured ~3.7 % in reality).
Returns a list of `FeedAlert(level, code, message)`.

## `h2iso.impurity_routing` — Flowsheet-level fate

### `route_impurities(config, result, injections, *, solubility_ppm=None)`

Traces impurity **injections** through a converged flowsheet solution and
reports where each one leaves the cascade.

```python
from h2iso.impurity_routing import route_impurities

report = route_impurities(
    config, result,
    {"CD2": {"CO": 0.804, "N2": 0.402, "He4": 0.402}},  # mol/h per column
)
report.by_destination()   # {"CD2_top": {"He4": ...}, "CD2": {...}}
report.frozen_columns()   # deposition locations
```

**Rules:** non-condensables follow the top streams (through downstream columns
and recycles, re-classified with each column's own window) until a terminal
stream; frozen species deposit in the column they enter; multi-destination
streams honour `config.splitter` ratios (otherwise each branch carries the full
flow, matching the sequential-modular solver) and the note is recorded in
`route.basis`; a walk re-entering an already-visited column is reported as
`recirculating`.

Each route also carries `terminal_kind`, the unambiguous terminus
classification (three mutually exclusive states):

| `terminal_kind` | meaning |
|---|---|
| `"purge_branch"` | routed into a real condenser purge branch |
| `"declared_product_end"` | reached a stream declared in `config.products` |
| `"undeclared_terminal_end"` | reached a leaf stream the flowsheet neither connects nor declares |
| `None` | the route never reaches a stream (frozen / dissolved / recirculating / vle_active) |

Read `route.exits_via_terminal_stream` and `route.enters_purge_branch` for those
questions. A route deserialized from a payload written before `terminal_kind`
existed carries `None` — treat that as "not classified", not as "not a
terminus".

**Legacy names — `status == "vent"` and `route.enters_vent`:** `"vent"` means
"reached a **terminal stream**", not "entered a vent". `enters_vent` returns
`True` for a plain product end and `False` for a real purge branch, so it cannot
answer "did the impurity enter a vent?". It is kept unchanged for backward
compatibility and is deprecated — use `terminal_kind` instead.

**Warns:** `UserWarning` for every freeze-out, forwarded from the single-column
disposition layer.

## `h2iso.purge` — Non-condensable purge branch (V1.2)

### `design_purge(column_result, he_flow_mol_h, purge, *, pressure_Pa, product_flow_mol_h)`

Models a vent in the condenser head space as a single equilibrium stage — the
*thermodynamic limit* for any staged dephlegmator. The vent temperature solves
`Σ K_i(T,P,x_top)·x_i = 1 − y_He`, so the helium enrichment `y_He` fixes both
the required subcooling and the condensable loss per mole of helium,
`(1 − y_He)/y_He`. Returns a `PurgeDesign` (vent temperature, loss breakdown,
tritium loss in T atoms, feasibility).

```python
from h2iso.purge import PurgeSpec, design_purge, max_feasible_enrichment

d = design_purge(cd2_result, 0.4018, PurgeSpec("CD2", 0.30), pressure_Pa=90_000)
d.loss_total_mol_h, d.tritium_loss_mol_h, d.feasible   # total, tritium, feasibility
max_feasible_enrichment(cd2_result, PurgeSpec("CD2", 0.5), pressure_Pa=90_000)
```

`max_feasible_enrichment()` returns the enrichment at which the vent would
reach the freezing floor of the condensate (the triple point of any species at
x ≥ 1 %), i.e. the feasibility cap; raising the vent pressure raises it.

### `route_impurities(..., purges={"CD2": PurgeSpec("CD2", 0.30)})`

With a purge configured, helium reaching that column leaves through
`"{column}_purge"` (status `"purge"`) instead of the top product, and the
co-vented condensable loss is designed with the helium flow that actually
arrives — `report.purge_designs` carries the result.
