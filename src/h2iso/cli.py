"""h2iso CLI — command-line interface for hydrogen isotope calculations.

Subcommands:
    h2iso flash   — Isothermal flash calculation
    h2iso column  — Solve a distillation column from JSON config
    h2iso export  — Convert column results between formats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from h2iso.species import SPECIES_ORDER


def _parse_composition(spec: str) -> np.ndarray:
    """Parse composition string like 'D2:0.98,DT:0.02' into 6-element array."""
    z = np.zeros(6)
    for pair in spec.split(","):
        parts = pair.strip().split(":")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid composition pair: '{pair}'. Use 'Species:fraction'."
            )
        name, val = parts[0].strip(), float(parts[1].strip())
        if name not in SPECIES_ORDER:
            raise ValueError(f"Unknown species '{name}'. Valid: {SPECIES_ORDER}")
        idx = SPECIES_ORDER.index(name)
        z[idx] = val
    if abs(z.sum() - 1.0) > 0.01:
        raise ValueError(f"Composition sums to {z.sum():.4f}, expected ~1.0")
    # Normalize
    z /= z.sum()
    return z


def cmd_flash(args: argparse.Namespace) -> None:
    """Execute flash subcommand."""
    from h2iso.vle.mixing import bubble_pressure, flash_TP, kvalue

    z = _parse_composition(args.z)
    T = args.T
    P = args.P

    K = kvalue(T, P, z)
    P_bub, _ = bubble_pressure(T, z)

    print(f"Flash at T = {T:.2f} K, P = {P:.0f} Pa")
    print(f"Bubble pressure: {P_bub:.0f} Pa")
    print()

    if P < P_bub:
        # Superheated or two-phase — do flash
        beta, x_liq, y_vap = flash_TP(T, P, z)
        print(f"Vapor fraction: {beta:.4f}")
        print()
        print(f"{'Species':<6} {'z_feed':<10} {'x_liq':<10} {'y_vap':<10} {'K_i':<10}")
        print("-" * 46)
        for i, sp in enumerate(SPECIES_ORDER):
            if z[i] > 1e-12 or x_liq[i] > 1e-12:
                print(
                    f"{sp:<6} {z[i]:<10.6f} {x_liq[i]:<10.6f} {y_vap[i]:<10.6f} {K[i]:<10.4f}"
                )
    else:
        # Subcooled liquid
        print("State: subcooled liquid (P > P_bubble)")
        print()
        print(f"{'Species':<6} {'z_feed':<10} {'K_i':<10}")
        print("-" * 26)
        for i, sp in enumerate(SPECIES_ORDER):
            if z[i] > 1e-12:
                print(f"{sp:<6} {z[i]:<10.6f} {K[i]:<10.4f}")


def cmd_column(args: argparse.Namespace) -> None:
    """Execute column subcommand."""
    from h2iso.mesh.column import Column, ColumnSpec
    from h2iso.mesh.continuation import ContinuationSolver
    from h2iso.mesh.export import export_csv, export_json

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        raise SystemExit(1)

    with open(config_path) as f:
        cfg = json.load(f)

    # Parse feed composition (support both flat and nested formats)
    feed_data = cfg.get("feed", cfg)
    if "composition_mole_fraction" in feed_data:
        feed_comp = feed_data["composition_mole_fraction"]
    else:
        feed_comp = cfg.get("feed_composition", {})
    feed = np.zeros(6)
    for sp, val in feed_comp.items():
        if sp in SPECIES_ORDER and val is not None:
            feed[SPECIES_ORDER.index(sp)] = val
    if feed.sum() == 0:
        print("Error: feed composition is all zeros", file=sys.stderr)
        raise SystemExit(1)
    feed /= feed.sum()

    col_cfg = cfg.get("column", {})
    n_stages = col_cfg.get("n_stages", col_cfg.get("total_stages", 15))
    feed_stage = col_cfg.get("feed_stage", n_stages // 2)
    pressure = col_cfg.get("pressure_Pa", col_cfg.get("pressure_top_Pa", 101325))
    reflux_ratio = col_cfg.get("reflux_ratio", 10.0)
    df_ratio = col_cfg.get(
        "distillate_to_feed", col_cfg.get("distillate_to_feed_ratio", 0.5)
    )
    feed_flow = feed_data.get("total_flow_mol_h", cfg.get("feed_flow_mol_per_h", 100.0))

    spec = ColumnSpec(
        n_stages=min(n_stages, 15),  # Start small for continuation
        feed_stage=min(feed_stage, 14),
        feed_flow=feed_flow,
        feed_composition=feed,
        pressure=pressure,
        reflux_ratio=reflux_ratio,
        distillate_to_feed=df_ratio,
    )

    # Use continuation if target > 15
    if n_stages > 15:
        solver = ContinuationSolver()
        if n_stages > 30:
            solver.add_step("N", target=30, n_substeps=1)
        substeps = max(1, (n_stages - 30) // 15)
        solver.add_step("N", target=n_stages, n_substeps=substeps)
        print(f"Solving {n_stages}-stage column with continuation...")
        result = solver.solve(spec)
        col_result = result.final
    else:
        print(f"Solving {n_stages}-stage column...")
        col = Column(spec)
        col_result = col.solve()

    # Output
    print(f"\nStatus: {col_result.convergence_info['status']}")
    print(f"Top composition:    {_format_comp(col_result.x_profile[0])}")
    print(f"Bottom composition: {_format_comp(col_result.x_profile[-1])}")
    print(
        f"T_top = {col_result.T_profile[0]:.2f} K, T_bot = {col_result.T_profile[-1]:.2f} K"
    )
    print(
        f"Q_cond = {col_result.condenser_duty:.1f} W, Q_reb = {col_result.reboiler_duty:.1f} W"
    )

    # Export
    out_dir = Path(args.output) if args.output else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    export_csv(col_result, out_dir / "profiles.csv")
    export_json(col_result, out_dir / "profiles.json")
    print(f"\nProfiles exported to {out_dir}/")


def cmd_export(args: argparse.Namespace) -> None:
    """Execute export subcommand."""
    from h2iso.mesh.column import ColumnResult
    from h2iso.mesh.export import export_csv, export_json, export_mat

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        raise SystemExit(1)

    with open(input_path) as f:
        data = json.load(f)

    # Support both flat and nested JSON formats
    if "profiles" in data:
        # Nested format from export_json
        profiles = data["profiles"]
        result = ColumnResult(
            T_profile=np.array(profiles["T"]),
            x_profile=np.array(profiles["x"]),
            y_profile=np.array(profiles["y"]),
            L_profile=np.array(profiles["L"]),
            V_profile=np.array(profiles["V"]),
            condenser_duty=data["heat_duties"]["condenser_W"],
            reboiler_duty=data["heat_duties"]["reboiler_W"],
            convergence_info=data.get("convergence", {}),
        )
    else:
        # Flat format
        result = ColumnResult(
            T_profile=np.array(data["T_profile"]),
            x_profile=np.array(data["x_profile"]),
            y_profile=np.array(data["y_profile"]),
            L_profile=np.array(data["L_profile"]),
            V_profile=np.array(data["V_profile"]),
            condenser_duty=data["condenser_duty"],
            reboiler_duty=data["reboiler_duty"],
            convergence_info=data.get("convergence_info", {}),
        )

    output = (
        Path(args.output) if args.output else input_path.with_suffix(f".{args.format}")
    )

    fmt = args.format
    if fmt == "csv":
        export_csv(result, output)
    elif fmt == "json":
        export_json(result, output)
    elif fmt == "mat":
        export_mat(result, output)
    else:
        print(f"Error: unknown format '{fmt}'. Use csv, json, or mat.", file=sys.stderr)
        raise SystemExit(1)

    print(f"Exported to {output}")


def cmd_flowsheet(args: argparse.Namespace) -> None:
    """Execute flowsheet subcommand."""
    from h2iso.flowsheet.schema import load_flowsheet
    from h2iso.flowsheet.solver import SequentialModularSolver
    from h2iso.mesh.export import export_csv

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        raise SystemExit(1)

    config = load_flowsheet(config_path)
    print(
        f"Flowsheet: {len(config.columns)} columns, {len(config.feeds)} feeds, "
        f"{len(config.tear_streams)} tear streams"
    )

    solver = SequentialModularSolver(
        config,
        method=args.method,
        continuation_substeps=3,
    )
    result = solver.solve(max_iter=args.max_iter, tol=args.tol)

    # Summary
    status = "CONVERGED" if result.converged else "NOT CONVERGED"
    print(f"\nStatus: {status}")
    print(f"Iterations: {result.iterations}")
    print(f"Tear residual: {result.tear_residual:.2e}")

    # Product streams
    print("\n--- Product Streams ---")
    for name, stream in sorted(result.streams.items()):
        if name.endswith("_distillate") or name.endswith("_bottoms"):
            comp_str = _format_comp(stream.composition)
            print(
                f"  {name}: flow={stream.flow:.2f} mol/h, T={stream.temperature:.2f} K"
            )
            print(f"    composition: {comp_str}")

    # Export
    out_dir = Path(args.output) if args.output else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Export column profiles
    for col_name, col_result in result.column_results.items():
        if col_result is not None:
            export_csv(col_result, out_dir / f"{col_name}_profiles.csv")

    # Export summary JSON
    summary = {
        "converged": result.converged,
        "iterations": result.iterations,
        "tear_residual": float(result.tear_residual),
        "method": args.method,
        "streams": {},
    }
    for name, stream in result.streams.items():
        summary["streams"][name] = {
            "flow_mol_h": float(stream.flow),
            "temperature_K": float(stream.temperature),
            "pressure_Pa": float(stream.pressure),
            "composition": {
                sp: float(stream.composition[i])
                for i, sp in enumerate(SPECIES_ORDER)
                if stream.composition[i] > 1e-12
            },
        }

    summary_path = out_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults exported to {out_dir}/")


def cmd_sweep(args: argparse.Namespace) -> None:
    """Execute sweep subcommand."""
    from h2iso.flowsheet.schema import load_flowsheet
    from h2iso.flowsheet.sweep import ParameterSweep

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        raise SystemExit(1)

    config = load_flowsheet(config_path)

    # Parse sweep values
    start, stop, step = args.start, args.stop, args.step
    if args.parameter == "n_stages":
        values = list(range(int(start), int(stop) + 1, int(step)))
    else:
        values = list(np.arange(start, stop + step * 0.5, step))

    print(f"Sweeping {args.parameter} on {args.column}: {values}")

    sweep = ParameterSweep(
        config,
        target_column=args.column,
        continuation_substeps=3,
        method="wegstein",
    )

    if args.parameter == "reflux_ratio":
        result = sweep.sweep_reflux_ratio(values, max_iter=args.max_iter, tol=args.tol)
    elif args.parameter == "n_stages":
        result = sweep.sweep_n_stages(values, max_iter=args.max_iter, tol=args.tol)
    elif args.parameter == "distillate_to_feed":
        result = sweep.sweep_distillate_to_feed(
            values, max_iter=args.max_iter, tol=args.tol
        )
    else:
        print(f"Error: unknown parameter '{args.parameter}'", file=sys.stderr)
        raise SystemExit(1)

    print(f"\nCompleted: {len(result.converged_points)}/{len(result.points)} converged")

    # Export
    out_dir = Path(args.output) if args.output else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sweep_results.json"
    result.to_json(out_path)
    print(f"Results exported to {out_path}")


def _format_comp(x: np.ndarray) -> str:
    """Format composition array as readable string."""
    parts = []
    for i, sp in enumerate(SPECIES_ORDER):
        if x[i] > 1e-6:
            parts.append(f"{sp}={x[i]:.4%}")
    return ", ".join(parts)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="h2iso",
        description="Hydrogen isotope cryogenic VLE and distillation solver",
    )
    parser.add_argument("--version", action="version", version="h2iso 0.1.0")
    subparsers = parser.add_subparsers(dest="command")

    # flash subcommand
    flash_p = subparsers.add_parser("flash", help="Isothermal flash calculation")
    flash_p.add_argument("--T", type=float, required=True, help="Temperature (K)")
    flash_p.add_argument("--P", type=float, required=True, help="Pressure (Pa)")
    flash_p.add_argument(
        "--z", type=str, required=True, help="Composition, e.g. 'D2:0.98,DT:0.02'"
    )

    # column subcommand
    col_p = subparsers.add_parser(
        "column", help="Solve distillation column from JSON config"
    )
    col_p.add_argument(
        "--config", type=str, required=True, help="Column config JSON file"
    )
    col_p.add_argument(
        "--output", type=str, default=None, help="Output directory (default: current)"
    )

    # flowsheet subcommand
    fs_p = subparsers.add_parser(
        "flowsheet", help="Solve multi-column flowsheet from JSON config"
    )
    fs_p.add_argument(
        "--config", type=str, required=True, help="Flowsheet config JSON file"
    )
    fs_p.add_argument(
        "--output", type=str, default=None, help="Output directory (default: current)"
    )
    fs_p.add_argument(
        "--max-iter",
        type=int,
        default=50,
        help="Max tear stream iterations (default: 50)",
    )
    fs_p.add_argument(
        "--tol", type=float, default=1e-4, help="Convergence tolerance (default: 1e-4)"
    )
    fs_p.add_argument(
        "--method",
        type=str,
        choices=["wegstein", "direct"],
        default="wegstein",
        help="Convergence method (default: wegstein)",
    )

    # sweep subcommand
    sw_p = subparsers.add_parser(
        "sweep", help="Parameter sweep over a flowsheet column"
    )
    sw_p.add_argument(
        "--config", type=str, required=True, help="Flowsheet config JSON file"
    )
    sw_p.add_argument(
        "--column", type=str, required=True, help="Target column name (e.g., CD2)"
    )
    sw_p.add_argument(
        "--parameter",
        type=str,
        required=True,
        choices=["reflux_ratio", "n_stages", "distillate_to_feed"],
        help="Parameter to sweep",
    )
    sw_p.add_argument("--start", type=float, required=True, help="Start value")
    sw_p.add_argument("--stop", type=float, required=True, help="Stop value")
    sw_p.add_argument("--step", type=float, required=True, help="Step size")
    sw_p.add_argument(
        "--output", type=str, default=None, help="Output directory (default: current)"
    )
    sw_p.add_argument(
        "--max-iter", type=int, default=50, help="Max iterations per solve"
    )
    sw_p.add_argument("--tol", type=float, default=1e-4, help="Convergence tolerance")

    # export subcommand
    exp_p = subparsers.add_parser(
        "export", help="Convert column results between formats"
    )
    exp_p.add_argument(
        "--input", type=str, required=True, help="Input JSON results file"
    )
    exp_p.add_argument(
        "--format",
        type=str,
        choices=["csv", "json", "mat"],
        default="csv",
        help="Output format",
    )
    exp_p.add_argument("--output", type=str, default=None, help="Output file path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        raise SystemExit(0)

    if args.command == "flash":
        cmd_flash(args)
    elif args.command == "column":
        cmd_column(args)
    elif args.command == "flowsheet":
        cmd_flowsheet(args)
    elif args.command == "sweep":
        cmd_sweep(args)
    elif args.command == "export":
        cmd_export(args)


if __name__ == "__main__":
    main()
