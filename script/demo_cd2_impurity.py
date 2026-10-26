#!/usr/bin/env python3
"""Demo: CD2 column with trace impurities.

Solves the 6-species CD2 core on the reference impurity fixture
(1% CO + 0.5% N2 + 0.5% He-4 in the NBI feed), then applies the impurity
disposition layer:

* He-4 -> leaves with the top product (non-condensable), diluting it;
* CO, N2 -> freeze out at 23-25 K (triple points 68/63 K): reported as
  deposition risks -- the phase-equilibrium model does not apply.

Outputs: a disposition table (console + CSV) and the diluted top-product
composition, written to ``<repo>/runs/20261009_cd2_impurity/``.

Run from the repository root::

    python script/demo_cd2_impurity.py
"""

import csv
import json
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import numpy as np  # noqa: E402

from h2iso.impurities import (  # noqa: E402
    column_impurity_disposition,
    dilute_top_product,
)
from h2iso.mesh.column import ColumnSpec  # noqa: E402
from h2iso.mesh.continuation import ContinuationSolver  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "wang2022" / "wang2022_issi_cd2_impurity.json"
OUT = REPO / "runs" / "20261009_cd2_impurity"
OUT.mkdir(parents=True, exist_ok=True)

fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
feed = fx["feed"]
z = np.array(
    [
        feed["composition_mole_fraction"][sp]
        for sp in ["H2", "HD", "HT", "D2", "DT", "T2"]
    ]
)

spec = ColumnSpec(
    n_stages=15,
    feed_stage=8,
    feed_flow=feed["total_flow_mol_h"],
    feed_composition=z,
    pressure=95_000.0,
    reflux_ratio=fx["column"]["reflux_ratio"],
    distillate_to_feed=fx["column"]["distillate_to_feed_ratio"],
)
print("solving CD2 (75 theoretical stages, continuation) ...")
solver = ContinuationSolver()
solver.add_step("N", target=30, n_substeps=1)
solver.add_step("N", target=75, n_substeps=3)
result = solver.solve(spec).final
assert result.convergence_info["success"]

t_min, t_max = float(result.T_profile[0]), float(result.T_profile[-1])
d_flow = fx["column"]["distillate_to_feed_ratio"] * feed["total_flow_mol_h"]
b_flow = feed["total_flow_mol_h"] - d_flow

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    disp = column_impurity_disposition(
        feed["impurities"],
        feed["total_flow_mol_h"],
        t_min,
        t_max,
        liquid_flow_mol_h=b_flow,
    )

print(
    f"\nCD2 window: {t_min:.2f}-{t_max:.2f} K  |  D = {d_flow:.3f} mol/h, "
    f"B = {b_flow:.3f} mol/h\n"
)
print(
    f"{'species':>8} {'status':>11} {'feed mol/h':>11} {'to top':>10} "
    f"{'dissolved':>10} {'frozen':>10}"
)
for d in disp:
    print(
        f"{d.species:>8} {d.status:>11} {d.feed_mol_h:>11.5f} "
        f"{d.to_top_mol_h:>10.6f} {d.dissolved_mol_h:>10.6f} "
        f"{d.frozen_mol_h:>10.5f}"
    )

to_top = {d.species: d.to_top_mol_h for d in disp if d.to_top_mol_h > 0}
x_dil, rel = dilute_top_product(
    {"D2": float(result.x_profile[0, 3]), "DT": float(result.x_profile[0, 4])},
    to_top,
    d_flow,
)
print(f"\ntop product (baseline) : D2 = {result.x_profile[0, 3]:.6f}")
print(
    f"top product (diluted)  : D2 = {x_dil['D2']:.6f}, "
    f"He4 = {x_dil.get('He4', 0.0):.6f}"
)
print(f"relative purity change : {rel:.3%}")
print("  -> dilution equals the He fraction by construction (flow-weighted);")
print("     the reference '< 0.5 %' band holds for He <= ~0.49 % of the feed.")

with open(OUT / "cd2_impurity_disposition.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(
        [
            "species",
            "status",
            "feed_mol_h",
            "to_top_mol_h",
            "dissolved_mol_h",
            "frozen_mol_h",
            "basis",
        ]
    )
    for d in disp:
        w.writerow(
            [
                d.species,
                d.status,
                f"{d.feed_mol_h:.8g}",
                f"{d.to_top_mol_h:.8g}",
                f"{d.dissolved_mol_h:.8g}",
                f"{d.frozen_mol_h:.8g}",
                d.basis,
            ]
        )

summary = {
    "column_window_K": [t_min, t_max],
    "distillate_mol_h": d_flow,
    "bottom_mol_h": b_flow,
    "disposition": [d.to_dict() for d in disp],
    "top_product_baseline": {"D2": float(result.x_profile[0, 3])},
    "top_product_diluted": x_dil,
    "relative_purity_change": rel,
    "warnings": [str(w.message) for w in caught],
}
(OUT / "cd2_impurity_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("\nwrote:", OUT)
