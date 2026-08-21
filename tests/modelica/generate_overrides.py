#!/usr/bin/env python3
"""Script for generating Modelica 0-D surrogate parameter override files (override_cycle.txt).

This script extracts high-fidelity steady-state results (separation factors SF,
temperatures T_top/T_bottom, and hydraulic holdup residence time tau) calculated by h2iso,
and formats them into OpenModelica simulation override files.

Usage:
    # 1. Export override files to scalar_1d_mapping and vector_5d_mapping from benchmark fixtures
    python generate_overrides.py

    # 2. Re-solve the flowsheet with h2iso solver before generating overrides
    python generate_overrides.py --solve

    # 3. Export to a specific directory
    python generate_overrides.py --target-dir ./scalar_1d_mapping
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Add src to path
H2ISO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(H2ISO_ROOT / "src"))

from h2iso.codegen.modelica_0d import (
    export_modelica_package,
    generate_cycle_override_file,
    generate_override_from_results,
)


def generate_from_solver(fixtures_dir: Path) -> tuple[dict, dict]:
    """Solve Wang 2022 ISS-I and ISS-O flowsheets in real time using h2iso solver."""
    from h2iso.io.flowsheet_io import load_flowsheet
    from h2iso.solver.sequential import SequentialModularSolver

    print("[INFO] Running h2iso SequentialModularSolver on Wang (2022) flowsheets...")

    # Solve ISS-O (3 columns)
    isso_file = fixtures_dir / "wang2022_isso.json"
    print(f"  -> Solving ISS-O flowsheet: {isso_file.name}")
    isso_config = load_flowsheet(isso_file)
    isso_solver = SequentialModularSolver(isso_config, method="wegstein", continuation_substeps=3)
    isso_res = isso_solver.solve(max_iter=50, tol=1e-4)
    if not isso_res.converged:
        print("[WARNING] ISS-O solve did not strictly converge. Using last iteration state.")

    # Convert solver state to override dictionary
    isso_data = {}
    for col_name, col_obj in isso_solver.columns.items():
        tau = getattr(col_obj, "tau", 1.0)
        isso_data[col_name] = {
            "T_top": float(col_obj.T[0]),
            "T_bottom": float(col_obj.T[-1]),
            "tau": float(tau),
            "m_top": [float(m) for m in col_obj.m_top],
            "m_bottom": [float(m) for m in col_obj.m_bottom],
        }

    # Solve ISS-I (4 columns)
    issi_file = fixtures_dir / "wang2022_issi.json"
    print(f"  -> Solving ISS-I flowsheet: {issi_file.name}")
    issi_config = load_flowsheet(issi_file)
    issi_solver = SequentialModularSolver(issi_config, method="wegstein", continuation_substeps=3)
    issi_res = issi_solver.solve(max_iter=50, tol=1e-4)
    if not issi_res.converged:
        print("[WARNING] ISS-I solve did not strictly converge. Using last iteration state.")

    issi_data = {}
    for col_name, col_obj in issi_solver.columns.items():
        tau = getattr(col_obj, "tau", 1.0)
        issi_data[col_name] = {
            "T_top": float(col_obj.T[0]),
            "T_bottom": float(col_obj.T[-1]),
            "tau": float(tau),
            "m_top": [float(m) for m in col_obj.m_top],
            "m_bottom": [float(m) for m in col_obj.m_bottom],
        }

    return issi_data, isso_data


def generate_overrides(
    output_dir: Path,
    solve_live: bool = False,
    fixtures_dir: Path | None = None,
) -> dict[str, Path]:
    """Generate override_cycle.txt and related files into output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if fixtures_dir is None:
        fixtures_dir = H2ISO_ROOT / "tests" / "fixtures" / "wang2022"

    if solve_live:
        issi_data, isso_data = generate_from_solver(fixtures_dir)
    else:
        # Load from benchmark JSON fixtures
        issi_file = fixtures_dir / "wang2022_issi_results.json"
        isso_file = fixtures_dir / "wang2022_isso_results.json"

        with open(issi_file, encoding="utf-8") as f:
            issi_data = json.load(f)
        with open(isso_file, encoding="utf-8") as f:
            isso_data = json.load(f)

    # 1. Generate override_cycle.txt
    cycle_override_content = generate_cycle_override_file(
        issi_results=issi_data,
        isso_results=isso_data,
        o_iss_prefix="o_iss.core",
        i_iss_prefix="i_iss.core",
    )
    cycle_override_file = output_dir / "override_cycle.txt"
    cycle_override_file.write_text(cycle_override_content, encoding="utf-8")
    print(f"[SUCCESS] Generated: {cycle_override_file}")

    # 2. Generate sub-system override files
    issi_override_content = generate_override_from_results(issi_data)
    issi_override_file = output_dir / "override_issi.txt"
    issi_override_file.write_text(issi_override_content, encoding="utf-8")

    isso_override_content = generate_override_from_results(isso_data)
    isso_override_file = output_dir / "override_isso.txt"
    isso_override_file.write_text(isso_override_content, encoding="utf-8")

    # 3. Export latest Modelica libraries
    export_modelica_package(output_dir)

    return {
        "override_cycle.txt": cycle_override_file,
        "override_issi.txt": issi_override_file,
        "override_isso.txt": isso_override_file,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate override_cycle.txt parameter files from h2iso solver results."
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=None,
        help="Target directory to write override files. If omitted, writes to both subdirectories.",
    )
    parser.add_argument(
        "--solve",
        action="store_true",
        help="Run real-time rigorous flowsheet solve using h2iso solver before generating overrides.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent

    if args.target_dir:
        targets = [Path(args.target_dir).resolve()]
    else:
        targets = [
            base_dir / "scalar_1d_mapping",
            base_dir / "vector_5d_mapping",
        ]

    for target in targets:
        print(f"\n[INFO] Generating Modelica surrogates & overrides in: {target}")
        generate_overrides(output_dir=target, solve_live=args.solve)

    print("\n[DONE] All override files generated successfully.")


if __name__ == "__main__":
    main()
