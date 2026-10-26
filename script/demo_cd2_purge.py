#!/usr/bin/env python3
"""CD2 helium purge branch -- V1.1 vs V1.2 comparison.

Solves the CFEDR ISS-I cascade once (6-isotope core), injects the
reference NBI impurity recipe at CD2, and compares two schemes:

* **V1.1** -- no dedicated vent: helium leaves with the CD2 top product
  (the WDS-D stream), which it contaminates and which therefore needs a
  downstream separation step;
* **V1.2** -- a purge branch in the CD2 condenser head space: helium is
  vented, the top product stays helium-free, and the price is the
  condensable (D2/DT/T2) co-vented with it -- designed with the
  equilibrium vent model in ``h2iso.purge``.

Outputs a sweep over the helium enrichment, the maximum feasible
enrichment (freezing floor of the condensate), pressure variants, and the
V1.1/V1.2 comparison table; CSV/JSON land in
``<repo>/runs/20261010_cd2_purge/``.

Run from the repository root::

    python script/demo_cd2_purge.py
"""

import csv
import json
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from h2iso.flowsheet.schema import load_flowsheet  # noqa: E402
from h2iso.flowsheet.solver import SequentialModularSolver  # noqa: E402
from h2iso.impurity_routing import route_impurities  # noqa: E402
from h2iso.purge import PurgeSpec, design_purge, max_feasible_enrichment  # noqa: E402
from h2iso.species import SPECIES_ORDER  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "wang2022" / "iss_i.json"
OUT = REPO / "runs" / "20261010_cd2_purge"
OUT.mkdir(parents=True, exist_ok=True)

NBI_FLOW = 80.357
RECIPE = {"CO": 0.01, "N2": 0.005, "He4": 0.005}
INJECTION = {"CD2": {sp: f * NBI_FLOW for sp, f in RECIPE.items()}}
HE_FLOW = INJECTION["CD2"]["He4"]

print("solving ISS-I (CFEDR inner fuel cycle) ...")
config = load_flowsheet(FIXTURE)
result = SequentialModularSolver(
    config, method="wegstein", continuation_substeps=3
).solve(max_iter=50, tol=1e-4)
assert result.converged
cd2 = result.column_results["CD2"]
D_flow = result.streams["CD2_distillate"].flow
P_top = next(c.pressure_top_Pa for c in config.columns if c.name == "CD2")
T_cond = float(cd2.T_profile[0])
x_D = {sp: float(v) for sp, v in zip(SPECIES_ORDER, cd2.x_profile[0])}

print(
    f"CD2: condensate {T_cond:.3f} K at {P_top / 1000:.0f} kPa, "
    f"distillate {D_flow:.3f} mol/h"
)
print(f"helium inflow (reference recipe): {HE_FLOW:.4f} mol/h\n")

summary = {
    "fixture": "iss_i.json",
    "recipe": RECIPE,
    "he_flow_mol_h": HE_FLOW,
    "cd2": {
        "T_condenser_K": T_cond,
        "pressure_Pa": float(P_top),
        "distillate_mol_h": float(D_flow),
        "top_composition": x_D,
    },
}

# ---------------------------------------------------------------- V1.1
print("=== V1.1 — no purge: helium leaves with the CD2 top product ===")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    rep11 = route_impurities(config, result, INJECTION)
for r in rep11.routes:
    print(
        f"  {r.species:>4} {r.status:>10} -> {r.destination:<10} "
        f"{r.flow_mol_h:.6f} mol/h"
    )
stream_after = D_flow + HE_FLOW
he_share = HE_FLOW / stream_after
print(
    f"  -> the WDS-D stream becomes {he_share:.3%} helium "
    f"({HE_FLOW:.3f}/{stream_after:.3f} mol/h); every isotope fraction is "
    f"diluted by {abs(1 / (1 + he_share) - 1):.2%}"
)
summary["v11"] = {
    "routes": rep11.to_dict()["routes"],
    "helium_in_top_product_mol_h": HE_FLOW,
    "helium_share_of_product": he_share,
    "product_dilution_relative": 1 / (1 + he_share) - 1,
}

# ---------------------------------------------------------------- V1.2
print("\n=== V1.2 — CD2 condenser purge branch ===")
enrichments = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60]
designs = []
print(
    f"{'y_He':>6} {'T_vent':>8} {'subcool':>8} {'loss':>9} {'% of D':>7} "
    f"{'T atoms/h':>10} {'feasible':>9}"
)
for y in enrichments:
    d = design_purge(
        cd2,
        HE_FLOW,
        PurgeSpec("CD2", y),
        pressure_Pa=P_top,
        product_flow_mol_h=D_flow,
    )
    designs.append(d.to_dict())
    flag = "yes" if d.feasible else f"NO!({d.limiting_species})"
    print(
        f"{y:>6.2f} {d.T_vent_K:>8.3f} {d.subcooling_K:>8.3f} "
        f"{d.loss_total_mol_h:>9.4f} {d.fraction_of_distillate:>7.2%} "
        f"{d.tritium_loss_mol_h:>10.4f} {flag:>9}"
    )

y_max = max_feasible_enrichment(cd2, PurgeSpec("CD2", 0.5), pressure_Pa=P_top)
d_max = design_purge(
    cd2, HE_FLOW, PurgeSpec("CD2", y_max), pressure_Pa=P_top, product_flow_mol_h=D_flow
)
print(
    f"\nfreezing floor {d_max.floor_K:.2f} K ({d_max.limiting_species}) limits the "
    f"enrichment to y_He = {y_max:.3f}"
)
print(
    f"at that limit: T_vent = {d_max.T_vent_K:.3f} K "
    f"({d_max.subcooling_K:.2f} K below the condenser), loss "
    f"{d_max.loss_total_mol_h:.4f} mol/h = {d_max.fraction_of_distillate:.2%} of D, "
    f"tritium {d_max.tritium_loss_mol_h:.4f} mol T-atoms/h"
)
print(
    "  loss composition: "
    + ", ".join(
        f"{sp}={q:.4f}" for sp, q in d_max.condensable_loss_mol_h.items() if q > 1e-4
    )
)
if not d_max.feasible:
    print(
        "  (the boundary itself sits inside the safety margin -- design a "
        "little below it)"
    )

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    rep12 = route_impurities(
        config, result, INJECTION, purges={"CD2": PurgeSpec("CD2", 0.30)}
    )
print("\nrouting with the purge active (y_He = 0.30):")
for r in rep12.routes:
    print(
        f"  {r.species:>4} {r.status:>10} -> {r.destination:<10} "
        f"{r.flow_mol_h:.6f} mol/h"
    )

# pressure lever
print("\n=== design lever: vent pressure ===")
print(f"{'P [kPa]':>8} {'y_He max':>9} {'loss at y_max':>14} {'% of D':>8}")
pressure_rows = []
for P in (90_000.0, 120_000.0, 200_000.0, 300_000.0):
    y_p = max_feasible_enrichment(cd2, PurgeSpec("CD2", 0.5), pressure_Pa=P)
    d_p = design_purge(
        cd2,
        HE_FLOW,
        PurgeSpec("CD2", min(y_p, 0.95 * y_p)),
        pressure_Pa=P,
        product_flow_mol_h=D_flow,
    )
    pressure_rows.append(
        {
            "pressure_kPa": P / 1000,
            "y_he_max": y_p,
            "design_y_he": min(y_p, 0.95 * y_p),
            "loss_mol_h": d_p.loss_total_mol_h,
            "fraction_of_distillate": d_p.fraction_of_distillate,
            "T_vent_K": d_p.T_vent_K,
        }
    )
    print(
        f"{P / 1000:>8.0f} {y_p:>9.3f} {d_p.loss_total_mol_h:>14.4f} "
        f"{d_p.fraction_of_distillate:>8.2%}"
    )

summary["v12"] = {
    "sweep": designs,
    "y_he_max": y_max,
    "design_at_limit": d_max.to_dict(),
    "routing_example": rep12.to_dict(),
    "pressure_variants": pressure_rows,
}

with open(OUT / "cd2_purge_sweep.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(
        [
            "y_he",
            "T_vent_K",
            "subcooling_K",
            "loss_mol_h",
            "loss_per_He",
            "loss_fraction_of_D",
            "tritium_loss_mol_T_atoms_h",
            "feasible",
            "limiting_species",
        ]
    )
    for d in designs:
        w.writerow(
            [
                f"{d['he_enrichment']:.3f}",
                f"{d['T_vent_K']:.4f}",
                f"{d['subcooling_K']:.4f}",
                f"{d['loss_total_mol_h']:.6g}",
                f"{d['loss_per_he_mol']:.4f}",
                f"{d['fraction_of_distillate']:.6g}",
                f"{d['tritium_loss_mol_h']:.6g}",
                d["feasible"],
                d["limiting_species"] or "",
            ]
        )

with open(OUT / "cd2_purge_pressure.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(pressure_rows[0]))
    w.writeheader()
    w.writerows(pressure_rows)

(OUT / "cd2_purge_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("\nwrote:", OUT)
