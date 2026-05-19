"""End-to-end Modelica simulation tests (B4).

Builds a minimal Modelica model that *uses* h2iso-generated pvap functions,
then invokes ``omc`` to ``simulate()`` it and reads back the numerical result.
Confirms the codegen → OMC → simulation path actually runs and produces
values consistent with h2iso Python references.

Distinct from ``test_modelica_compile.py``:
  * compile test runs ``checkModel`` (syntax / type check only)
  * this test runs ``simulate`` (full integration + result file read-back)

If ``omc`` is not available on PATH, all tests in this module are skipped.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from h2iso.codegen.modelica_records import (
    generate_vle_functions,
    pvap_reference,
)

OMC = shutil.which("omc")
pytestmark = pytest.mark.skipif(
    OMC is None, reason="OpenModelica `omc` not on PATH; skipping E2E simulate tests"
)


def _run_omc_script(workdir: Path, script: str, timeout: int = 180) -> tuple[int, str]:
    """Run an .mos script with omc; return (returncode, combined output)."""
    script_path = workdir / "_simulate.mos"
    script_path.write_text(script)
    proc = subprocess.run(
        [OMC, str(script_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workdir),
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _parse_simulate_csv(csv_path: Path, varname: str) -> tuple[float, float]:
    """Return (t_final, y_final) for the named variable from OMC CSV output."""
    rows = csv_path.read_text().splitlines()
    header = [c.strip().strip('"') for c in rows[0].split(",")]
    assert varname in header, f"{varname} not in {header}"
    idx_t = header.index("time")
    idx_y = header.index(varname)
    last = rows[-1].split(",")
    return float(last[idx_t]), float(last[idx_y])


# ---------------------------------------------------------------------------
# Test 1: trivial model consuming pvap_H2 — confirms simulate() path works
# ---------------------------------------------------------------------------


def test_pvap_consumer_simulate(tmp_path):
    """Simulate a trivial model y = pvap_H2(T(t)) with linearly ramping T.

    Verifies the full path: codegen → loadFile → buildModel → simulate →
    CSV result → matches Python reference.
    """
    pvap_dir = tmp_path / "pvap"
    generate_vle_functions(pvap_dir)

    model = tmp_path / "PvapDemo.mo"
    model.write_text(
        """
model PvapDemo
  Real T(start = 20.0);
  Real p_h2;
equation
  der(T) = 1.0;                 // K/s ramp
  p_h2 = pvap_H2(T);
end PvapDemo;
"""
    )

    script = (
        f'loadFile("{(pvap_dir / "pvap_H2.mo").as_posix()}"); getErrorString();\n'
        f'loadFile("{model.as_posix()}"); getErrorString();\n'
        'simulate(PvapDemo, stopTime=10.0, numberOfIntervals=50, '
        'outputFormat="csv"); getErrorString();\n'
    )
    rc, out = _run_omc_script(tmp_path, script)
    assert rc == 0, f"omc failed (rc={rc}):\n{out}"
    lowered = out.lower()
    assert "error" not in lowered or "0 errors" in lowered, f"omc errors:\n{out}"

    csv = tmp_path / "PvapDemo_res.csv"
    assert csv.exists(), (
        f"expected CSV at {csv}; tmp dir: {sorted(p.name for p in tmp_path.iterdir())}"
    )

    t_final, p_final = _parse_simulate_csv(csv, "p_h2")
    assert t_final == pytest.approx(10.0, rel=1e-3)

    # At t=10 s, T should be 30 K. Compare to Python reference.
    p_ref = pvap_reference(30.0, "H2")
    rel = abs(p_final - p_ref) / p_ref
    assert rel < 1e-3, f"pvap@30K mismatch: omc={p_final}, ref={p_ref}, rel={rel:.3e}"


# ---------------------------------------------------------------------------
# Test 2: multi-species pvap ratio — confirms each species function simulates
# ---------------------------------------------------------------------------


def test_multispecies_pvap_simulate(tmp_path):
    """Simulate p_T2 / p_H2 ratio at fixed T and compare to Python."""
    pvap_dir = tmp_path / "pvap"
    generate_vle_functions(pvap_dir)

    model = tmp_path / "RatioDemo.mo"
    model.write_text(
        """
model RatioDemo
  parameter Real T = 25.0;
  Real p_h2;
  Real p_t2;
  Real ratio;
  Real dummy(start = 0.0);
equation
  der(dummy) = 1.0;
  p_h2 = pvap_H2(T);
  p_t2 = pvap_T2(T);
  ratio = p_t2 / p_h2;
end RatioDemo;
"""
    )

    script = (
        f'loadFile("{(pvap_dir / "pvap_H2.mo").as_posix()}"); getErrorString();\n'
        f'loadFile("{(pvap_dir / "pvap_T2.mo").as_posix()}"); getErrorString();\n'
        f'loadFile("{model.as_posix()}"); getErrorString();\n'
        'simulate(RatioDemo, stopTime=1.0, numberOfIntervals=5, '
        'outputFormat="csv"); getErrorString();\n'
    )
    rc, out = _run_omc_script(tmp_path, script)
    assert rc == 0, f"omc failed:\n{out}"

    csv = tmp_path / "RatioDemo_res.csv"
    assert csv.exists()

    _, ratio_omc = _parse_simulate_csv(csv, "ratio")
    ratio_ref = pvap_reference(25.0, "T2") / pvap_reference(25.0, "H2")
    rel = abs(ratio_omc - ratio_ref) / ratio_ref
    assert rel < 1e-4, (
        f"T2/H2 ratio @25K mismatch: omc={ratio_omc}, ref={ratio_ref}, rel={rel:.3e}"
    )


# ---------------------------------------------------------------------------
# Test 3: end time and step count — confirms numerical integration ran
# ---------------------------------------------------------------------------


def test_simulate_integrator_steps(tmp_path):
    """A 100-step ramp should produce 100 + 1 rows in CSV output."""
    pvap_dir = tmp_path / "pvap"
    generate_vle_functions(pvap_dir)

    model = tmp_path / "StepCheck.mo"
    model.write_text(
        """
model StepCheck
  Real T(start = 20.0);
  Real p;
equation
  der(T) = 1.0;
  p = pvap_H2(T);
end StepCheck;
"""
    )

    script = (
        f'loadFile("{(pvap_dir / "pvap_H2.mo").as_posix()}"); getErrorString();\n'
        f'loadFile("{model.as_posix()}"); getErrorString();\n'
        'simulate(StepCheck, stopTime=5.0, numberOfIntervals=100, '
        'outputFormat="csv"); getErrorString();\n'
    )
    rc, out = _run_omc_script(tmp_path, script)
    assert rc == 0, f"omc failed:\n{out}"

    csv = tmp_path / "StepCheck_res.csv"
    rows = csv.read_text().splitlines()
    # Header + (intervals + 1) data rows; OMC may add events, allow ±5
    assert 95 <= len(rows) - 1 <= 110, f"expected ~101 rows, got {len(rows) - 1}"
