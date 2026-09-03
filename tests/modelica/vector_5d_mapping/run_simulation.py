"""Execution runner for verifying Generic_ISS & Generic_ISS_Adapters integration in example_model.mo.

Invokes OpenModelica compiler (`omc`), executes the coupled plant cycle simulation,
and generates the verification plot.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from h2iso.codegen import export_modelica_package


def run_omc_script(script_name: str, work_dir: Path) -> bool:
    """Run an .mos script using omc."""
    omc = shutil.which("omc")
    if not omc:
        default_omc = Path(r"C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe")
        if default_omc.exists():
            omc = str(default_omc)
        else:
            print("[ERROR] OpenModelica 'omc' compiler was not found on PATH or default directory.")
            return False

    script_path = work_dir / script_name
    if not script_path.exists():
        print(f"[ERROR] Script not found: {script_path}")
        return False

    print(f"[INFO] Executing OMC simulation: {script_name} ...")
    proc = subprocess.run(
        [omc, script_name],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    if "The simulation finished successfully." in combined:
        print("[SUCCESS] Simulation completed successfully!")
        return True
    else:
        print(f"[WARNING] OMC Output:\n{combined}")
        return proc.returncode == 0


def main():
    base_dir = Path(__file__).parent

    # 1. 自动生成并导出最新的 Generic_ISS.mo, Generic_ISS_Adapters.mo 与 override_cycle.txt
    print("[INFO] Exporting Modelica libraries and parameter override files...")
    export_modelica_package(base_dir)

    # 2. 运行 example_model.Cycle 集成验证仿真
    success = run_omc_script("simulate_cycle.mos", base_dir)
    if not success:
        print("[ERROR] simulate_cycle.mos failed.")
        sys.exit(1)

    # 3. 生成验证分析图表
    plot_script = base_dir / "plot_results.py"
    if plot_script.exists():
        print("[INFO] Generating trajectory visualization plots...")
        subprocess.run([sys.executable, str(plot_script)], cwd=str(base_dir), check=True)

    print("\n[DONE] Generic_ISS & Generic_ISS_Adapters integration verification in example_model.mo finished successfully.")


if __name__ == "__main__":
    main()
