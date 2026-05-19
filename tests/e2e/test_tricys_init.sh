#!/usr/bin/env bash
# End-to-end script: h2iso solve -> generate .mo + .mos -> omc syntax check.
# Skips gracefully when `omc` is not available.
set -euo pipefail

if ! command -v omc >/dev/null 2>&1; then
    echo "SKIP: OpenModelica 'omc' not on PATH"
    exit 0
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "[1/3] Generating Modelica species records and pvap functions"
python - <<PY
from pathlib import Path
from h2iso.codegen.modelica_records import generate_species_records, generate_vle_functions
out = Path("$WORKDIR")
generate_species_records(out / "records")
generate_vle_functions(out / "pvap")
print(f"Generated to {out}")
PY

echo "[2/3] Solving a small CD2 column and emitting init script"
python - <<PY
import numpy as np
from pathlib import Path
from h2iso.mesh.column import ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver
from h2iso.codegen.modelica_init import generate_init_script
from h2iso.species import N_SPECIES

feed = np.full(N_SPECIES, 1.0 / N_SPECIES)
spec = ColumnSpec(
    n_stages=10, feed_stage=5, feed_flow=10.0,
    feed_composition=feed, pressure=1.0e5,
    reflux_ratio=1.5, distillate_to_feed=0.5,
)
solver = ContinuationSolver()
solver.add_step("N", target=10, n_substeps=1)
result = solver.solve(spec).final
assert result.convergence_info["success"], "column failed to converge"
Path("$WORKDIR/init.mos").write_text(generate_init_script(result, "TestPkg.MyColumn"))
print("Init script written.")
PY

echo "[3/3] Running omc checkModel on each generated .mo"
cd "$WORKDIR"
SCRIPT="$WORKDIR/_check.mos"
{
    echo 'loadModel(Modelica); getErrorString();'
    for f in records/*.mo pvap/*.mo; do
        echo "loadFile(\"$WORKDIR/$f\"); getErrorString();"
        cls="$(basename "$f" .mo)"
        echo "print(checkModel($cls)); print(\"\\n\"); getErrorString();"
    done
} > "$SCRIPT"

if omc "$SCRIPT" 2>&1 | tee "$WORKDIR/_omc.log" | grep -iE "error|failed" \
        | grep -viE "0 errors|^Class" ; then
    echo "ERROR: omc reported issues; see $WORKDIR/_omc.log" >&2
    exit 1
fi

echo "All Modelica codegen artifacts compiled cleanly."
