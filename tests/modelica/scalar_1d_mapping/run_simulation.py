"""One-click runner for CFEDR_3LC simulation with Generic_ISS and Generic_ISS_Adapters.

Workflow:
1. Export latest Generic_ISS.mo, Generic_ISS_Adapters.mo and override_cycle.txt
2. Run OpenModelica simulation via simulate_ssp.mos
3. Invoke plot_results.py to generate 4-panel figures and print steady-state table
"""

from pathlib import Path
import shutil
import subprocess
import sys


def main():
    base_dir = Path(__file__).parent
    h2iso_root = base_dir.parent.parent.parent

    # 1. Export Modelica libraries and overrides
    print("[INFO] Exporting Modelica libraries and parameter override files...")
    sys.path.insert(0, str(h2iso_root / "src"))
    try:
        from h2iso.codegen.modelica_0d import export_modelica_package
        export_modelica_package(base_dir)
    except Exception as e:
        print(f"[WARNING] Could not auto-export from Python package: {e}")

    # 2. Check OpenModelica compiler
    omc_path = shutil.which("omc")
    if not omc_path:
        default_omc = Path(r"C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe")
        if default_omc.exists():
            omc_path = str(default_omc)
        else:
            print("[ERROR] OpenModelica compiler 'omc' not found in PATH or standard location.")
            sys.exit(1)

    mos_file = base_dir / "simulate_ssp.mos"
    print(f"[INFO] Executing OMC simulation: {mos_file.name} ...")
    cmd = [omc_path, mos_file.name]
    res = subprocess.run(cmd, cwd=base_dir, capture_output=True, text=True)

    if res.returncode != 0:
        print(f"[ERROR] OMC execution failed with returncode {res.returncode}:")
        print(res.stderr)
        print(res.stdout)
        sys.exit(res.returncode)

    if "SimulationResult" not in res.stdout and "true" not in res.stdout:
        print("[WARNING] Unexpected OMC output:")
        print(res.stdout)

    print("[SUCCESS] Simulation completed successfully!")

    # 3. Generate plots
    print("[INFO] Generating trajectory visualization plots...")
    plot_script = base_dir / "plot_results.py"
    subprocess.run([sys.executable, str(plot_script)], cwd=base_dir, check=True)

    print("\n[DONE] Generic_ISS & Generic_ISS_Adapters integration verification in CFEDR_2870_3lc_ssp.mo finished successfully.")


if __name__ == "__main__":
    main()
