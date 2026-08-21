"""E2E test integrating Generic_ISS Core and Adapters into full fuel cycle plant model."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
import pytest

from h2iso.codegen.modelica_0d import export_modelica_package

OMC = shutil.which("omc")
pytestmark = pytest.mark.skipif(
    OMC is None, reason="OpenModelica `omc` not on PATH; skipping E2E tests"
)


def _run_omc_script(workdir: Path, script: str, timeout: int = 120) -> tuple[int, str]:
    """Run an .mos script with omc; return (returncode, combined output)."""
    script_path = workdir / "_run_cycle.mos"
    script_path.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [OMC, str(script_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workdir),
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_generic_iss_adapters_in_plant_cycle(tmp_path):
    """Test integrating Generic_ISS_Adapters into a full-cycle Modelica model."""
    # 1. Export Generic_ISS.mo, Generic_ISS_Adapters.mo, and override_cycle.txt
    pkg_files = export_modelica_package(tmp_path)
    assert "Generic_ISS.mo" in pkg_files
    assert "Generic_ISS_Adapters.mo" in pkg_files
    assert "override_cycle.txt" in pkg_files

    # 2. Build a full fuel-cycle test model instantiating ISS_I_Adapter and ISS_O_Adapter
    plant_mo = tmp_path / "PlantCycle.mo"
    plant_mo.write_text(
        """
package PlantCycle
  model FullCycleTest
    // 实例化 ISS 适配器单元
    Generic_ISS_Adapters.ISS_I_Adapter i_iss;
    Generic_ISS_Adapters.ISS_O_Adapter o_iss;

    // 动态进料源 (模拟电站循环 5D 质量流量 g/h: [T, D, H, He, Imp])
    Real feed_tep[5];
    Real feed_wds[5];
    Real feed_tes[5];
    Real feed_cps[5];

    Real total_T_product;
  equation
    // 模拟周期性放电进料流
    feed_tep = {10.0, 30.0, 1.0, 0.0, 0.0};
    feed_wds = {0.05, 0.1, 800.0, 0.0, 0.0};
    feed_tes = {5.0, 0.0, 300.0, 0.0, 0.0};
    feed_cps = {0.0, 0.0, 0.0, 0.0, 0.0};

    // 连接端口
    i_iss.from_TEP_FCU = feed_tep;
    i_iss.from_NBI = {0,0,0,0,0};

    o_iss.from_WDS = feed_wds;
    o_iss.from_TES = feed_tes;
    o_iss.from_CPS = feed_cps;

    // 汇总高纯产氚流
    total_T_product = i_iss.to_SDS[1] + o_iss.to_SDS[1];
  end FullCycleTest;
end PlantCycle;
""",
        encoding="utf-8",
    )

    # 3. Simulate with omc and override_cycle.txt
    script = f"""
loadFile("{(tmp_path / "Generic_ISS.mo").as_posix()}"); getErrorString();
loadFile("{(tmp_path / "Generic_ISS_Adapters.mo").as_posix()}"); getErrorString();
loadFile("{(plant_mo).as_posix()}"); getErrorString();

simulate(PlantCycle.FullCycleTest, startTime=0, stopTime=100, numberOfIntervals=100,
         simflags="-overrideFile override_cycle.txt", outputFormat="csv"); getErrorString();
"""
    rc, out = _run_omc_script(tmp_path, script)
    assert rc == 0, f"omc failed (rc={rc}):\n{out}"
    assert "error" not in out.lower() or "0 errors" in out.lower(), f"omc errors:\n{out}"

    # 4. Verify CSV results
    csv_file = tmp_path / "PlantCycle.FullCycleTest_res.csv"
    assert csv_file.exists(), f"Missing CSV result file: {list(tmp_path.iterdir())}"

    lines = csv_file.read_text(encoding="utf-8").splitlines()
    header = [c.strip().strip('"') for c in lines[0].split(",")]
    assert "total_T_product" in header
    last_row = [float(v) for v in lines[-1].split(",")]
    idx_t = header.index("total_T_product")
    assert last_row[idx_t] > 0.0, f"Expected positive T product, got {last_row[idx_t]}"
