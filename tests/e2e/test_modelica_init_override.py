"""End-to-end: h2iso ``-overrideFile`` init export loads and simulates in OpenModelica.

Builds a minimal Modelica model that declares **exactly** the variables
h2iso exports (``T_init``, ``x_*_init``, ``y_*_init``, ``L_init``,
``V_init``, ``Q_cond``, ``Q_reb``, plus the optional-export ``holdup_l_init``,
``holdup_v_init``, ``murphree_eff``), generates the override file from a
synthetic :class:`ColumnResult`, then runs ``omc simulate`` with
``-overrideFile`` and checks:

1. OMC reports no "override variable name not found" warnings (i.e. the
   exported names all exist in the model);
2. a state initialised from ``holdup_l_init`` actually starts at the
   overridden value (proves values are applied, not just parsed).

This is the B.4-style validation: "the exported init values can be loaded
and simulated by a dynamic column model", with OpenModelica standing in for
tricys.  Distinguished from ``test_tricys_init.sh`` (which only syntax-checks
generated ``.mo`` files and never executes the init script).

Skipped when ``omc`` is not on PATH.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.codegen.modelica_init import generate_override_file
from h2iso.mesh.column import ColumnResult

OMC = shutil.which("omc")
pytestmark = pytest.mark.skipif(
    OMC is None, reason="OpenModelica `omc` not on PATH; skipping e2e test"
)

N = 3
SPECIES = ["H2", "HD", "HT", "D2", "DT", "T2"]

_MODEL_TEMPLATE = """\
model MiniCD
  parameter Integer N = {n};
  parameter Real T_init[N] = fill(24.0, N) annotation(Evaluate=false);
{species_params}
  parameter Real L_init[N] = fill(0.0, N) annotation(Evaluate=false);
  parameter Real V_init[N] = fill(0.0, N) annotation(Evaluate=false);
  parameter Real Q_cond = 0.0 annotation(Evaluate=false);
  parameter Real Q_reb = 0.0 annotation(Evaluate=false);
  parameter Real holdup_l_init[N] = fill(0.001, N) annotation(Evaluate=false);
  parameter Real holdup_v_init[N] = fill(0.0001, N) annotation(Evaluate=false);
  parameter Real murphree_eff[N, 6] = fill(1.0, N, 6) annotation(Evaluate=false);
  Real holdup_l[N](start = holdup_l_init, each fixed = true);
  output Real check_v1 "reads holdup_v_init[1] so parameter overrides are visible";
  output Real check_m11 "reads murphree_eff[1,1] (2-D element override check)";
equation
  der(holdup_l) = -10.0 * (holdup_l - holdup_l_init);
  check_v1 = holdup_v_init[1];
  check_m11 = murphree_eff[1, 1];
end MiniCD;
"""


def _make_model() -> str:
    lines = []
    for sp in SPECIES:
        lines.append(
            f"  parameter Real x_{sp}_init[N] = fill(0.0, N) "
            "annotation(Evaluate=false);"
        )
    for sp in SPECIES:
        lines.append(
            f"  parameter Real y_{sp}_init[N] = fill(0.0, N) "
            "annotation(Evaluate=false);"
        )
    return _MODEL_TEMPLATE.format(n=N, species_params="\n".join(lines))


def _make_result() -> ColumnResult:
    """Synthetic result with distinctive holdup values (no solver needed)."""
    x = np.full((N, 6), 1.0 / 6.0)
    y = np.full((N, 6), 1.0 / 6.0)
    result = ColumnResult(
        T_profile=np.linspace(23.0, 24.0, N),
        x_profile=x,
        y_profile=y,
        L_profile=np.full(N, 10.0),
        V_profile=np.full(N, 11.0),
        condenser_duty=-100.0,
        reboiler_duty=100.0,
        convergence_info={"status": "synthetic"},
    )
    result.holdup_l_profile = np.array([0.5, 0.6, 0.7])  # distinctive values
    result.holdup_v_profile = np.array([0.05, 0.06, 0.07])
    result.murphree_eff = np.full((N, 6), 0.85)
    return result


def test_override_file_simulates_and_applies(tmp_path: Path):
    (tmp_path / "mini.mo").write_text(_make_model(), encoding="utf-8")
    override = generate_override_file(_make_result(), prefix="")
    (tmp_path / "init_override.txt").write_text(override, encoding="utf-8")

    mos = (
        'loadFile("mini.mo"); getErrorString();\n'
        "simulate(MiniCD, startTime=0, stopTime=1.0, numberOfIntervals=10,\n"
        '         simflags="-overrideFile init_override.txt",\n'
        '         outputFormat="csv", fileNamePrefix="mini_result",\n'
        '         variableFilter="holdup_l.*|check_v1|check_m11");\n'
        "getErrorString();\n"
    )
    (tmp_path / "_run.mos").write_text(mos, encoding="utf-8")

    proc = subprocess.run(
        [OMC, "_run.mos"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = proc.stdout + proc.stderr

    # 1. no unresolved override names
    not_found = re.findall(r"override variable name not found in model: (\S+)", output)
    assert not not_found, f"unresolved override names: {not_found}\n{output[-2000:]}"
    assert "The simulation finished successfully" in output or proc.returncode == 0

    # 2. the state initialised from holdup_l_init starts at the overridden value
    csv_path = tmp_path / "mini_result_res.csv"
    assert csv_path.exists(), f"result file missing; omc output:\n{output[-2000:]}"
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        first_row = next(reader)

    def col(name: str) -> float:
        idx = [i for i, h in enumerate(header) if h.strip('"') == name]
        assert idx, f"column {name} not in {header}"
        return float(first_row[idx[0]])

    assert col("holdup_l[1]") == pytest.approx(0.5, abs=1e-9)
    assert col("holdup_l[2]") == pytest.approx(0.6, abs=1e-9)
    # parameter override visible through the algebraic pass-through
    assert col("check_v1") == pytest.approx(0.05, abs=1e-9)
    # 2-D element override syntax works
    assert col("check_m11") == pytest.approx(0.85, abs=1e-9)
