#!/usr/bin/env python3
"""Demo: impurity fate in the full ISS cascades.

Solves both Wang 2022 cascades with the plain 6-isotope core, then routes
the reference impurity recipe (1 % CO + 0.5 % N2 + 0.5 % He-4 of an
80.357 mol/h NBI feed) injected at the D2 column (CD2), as a tracer:

* ISS-I (CFEDR inner fuel cycle, 3 columns) -- CD2 top is the WDS-D
  product, so helium ends up diluting that product stream;
* ISS-O (outer fuel cycle, 3 columns + equilibrator) -- CD2 top is
  recycled to CD1, so helium exits the cascade with the H2-rich exhaust
  to the environment.

CO / N2 freeze out in CD2 in both cases (deposition risk, warnings).

Outputs: route tables (console) + CSV/JSON under
``<repo>/runs/20261010_iss_impurity/``.

Run from the repository root::

    python script/demo_iss_impurity.py
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
from h2iso.impurities import check_feed_impurities  # noqa: E402
from h2iso.impurity_routing import route_impurities  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "wang2022"
OUT = REPO / "runs" / "20261010_iss_impurity"
OUT.mkdir(parents=True, exist_ok=True)

# Reference recipe: fractions of an 80.357 mol/h NBI feed -> mol/h
NBI_FLOW = 80.357
RECIPE = {"CO": 0.01, "N2": 0.005, "He4": 0.005}
INJECTION = {"CD2": {sp: f * NBI_FLOW for sp, f in RECIPE.items()}}

CASES = [
    ("ISS-I (CFEDR inner fuel cycle)", "iss_i.json"),
    ("ISS-O (outer fuel cycle)", "wang2022_isso.json"),
]

print("=== feed alerts (reference NBI recipe) ===")
for alert in check_feed_impurities(RECIPE):
    print(f"[{alert.level:>8}] {alert.code}: {alert.message}")

summary = {"recipe": RECIPE, "nbi_flow_mol_h": NBI_FLOW, "cases": {}}

for title, fixture in CASES:
    print(f"\n=== {title} [{fixture}] ===")
    config = load_flowsheet(FIXTURES / fixture)
    solver = SequentialModularSolver(config, method="wegstein", continuation_substeps=3)
    result = solver.solve(max_iter=50, tol=1e-4)
    print(
        f"base solve: converged={result.converged} "
        f"iterations={result.iterations} residual={result.tear_residual:.2e}"
    )
    assert result.converged

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = route_impurities(config, result, INJECTION)

    print(
        f"\n{'species':>8} {'entry':>6} {'status':>14} {'destination':>12} "
        f"{'mol/h':>10}  path"
    )
    for r in report.routes:
        path = " -> ".join(r.path)
        print(
            f"{r.species:>8} {r.entry_column:>6} {r.status:>14} "
            f"{r.destination:>12} {r.flow_mol_h:>10.5g}  {path}"
        )

    print("\nwhere each impurity ends up (mol/h):")
    for dest, comp in report.by_destination().items():
        desc = config.products.get(dest, "")
        tag = f" ({desc})" if desc else ""
        parts = ", ".join(f"{sp}={q:.5f}" for sp, q in comp.items())
        print(f"  {dest}{tag}: {parts}")

    print(
        "\ncolumn windows (K): "
        + ", ".join(
            f"{name} {float(min(cr.T_profile)):.2f}-{float(max(cr.T_profile)):.2f}"
            for name, cr in result.column_results.items()
        )
    )
    print(f"captured warnings: {len(caught)}")
    for w in caught:
        print(f"  ! {w.message}")

    tag = "iss_i" if "iss_i" in fixture else "iss_o"
    with open(OUT / f"{tag}_routes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "species",
                "entry_column",
                "status",
                "destination",
                "flow_mol_h",
                "path",
                "basis",
            ]
        )
        for r in report.routes:
            w.writerow(
                [
                    r.species,
                    r.entry_column,
                    r.status,
                    r.destination,
                    f"{r.flow_mol_h:.8g}",
                    " -> ".join(r.path),
                    r.basis,
                ]
            )

    case = report.to_dict()
    case["products"] = config.products
    case["base_solve"] = {
        "converged": bool(result.converged),
        "iterations": int(result.iterations),
        "tear_residual": float(result.tear_residual),
    }
    summary["cases"][tag] = case

(OUT / "iss_impurity_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("\nwrote:", OUT)
