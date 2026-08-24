"""ISS-O flowsheet UQ validation case.

Runs Sobol screening + LHS Monte Carlo on the Wang 2022 ISS-O 3-column
flowsheet (CD1→CD2→equilibrator→CD3, with CD3_top recycle to CD2).

Two modes:
  --fast  No recycle (3 columns sequential, ~0.6 s/solve), 12-stage columns
          Suitable for CI and rapid parameter screening.
  --full  Full recycle flowsheet with continuation, 60/70/60-stage columns
          (~17 s/solve). For publication-grade results.

Usage:
    python -m h2iso.uq.run_isso              # fast mode (no recycle, CI)
    python -m h2iso.uq.run_isso --full       # full ISS-O with recycles
    python -m h2iso.uq.run_isso --mc-n 500 --sobol-n 16 --seed 123
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import numpy as np

from h2iso.flowsheet.schema import FlowsheetConfig, load_flowsheet
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.uq import Parameter, ParameterSpace, UQStudy
from h2iso.uq.qoi import qoi_isso_compact, qoi_isso_compact_labels

FIXTURE_PATH = "tests/fixtures/wang2022/wang2022_isso.json"

# ── Baseline ISS-O parameters (Wang 2022 Table 2 + Table 5) ──────────

BASELINE = {
    "cols": {
        "CD1": {"R": 6, "DF": 0.9948, "P": 95000.0, "n_stages": 60},
        "CD2": {"R": 8, "DF": 0.98625, "P": 95000.0, "n_stages": 70},
        "CD3": {"R": 18, "DF": 0.73225, "P": 95000.0, "n_stages": 60},
    },
    "feeds": {
        "WDS": {"flow": 280.0, "H2": 0.9975152, "HD": 0.00246, "HT": 0.0000248},
        "TES": {"flow": 160.0, "H2": 0.9925, "HT": 0.0075},
    },
    "fast_stages": 12,
}


def build_parameter_space(full: bool = False) -> ParameterSpace:
    """Define the UQ parameter space for ISS-O operational perturbations.

    Full mode (with recycles, ~17 s/solve): 8 parameters
      - Refux ratios (3)
      - Feed flows (2)
      - Pressures (3)

    Fast mode (no recycle, ~0.6 s/solve): 11 parameters
      - Refux ratios (3)
      - D/F ratios (3)
      - Feed flows (2)
      - Pressures (3)
    """
    params = []

    # ── Refux ratios (3 columns) ─────────────────────────────────
    for col, bl in BASELINE["cols"].items():
        R = bl["R"]
        params.append(
            Parameter(
                name=f"{col}.R",
                distribution="normal",
                params={"mu": R, "sigma": 0.03 * R},
                bounds=(0.5 * R, 2.0 * R),
                description=f"{col} reflux ratio",
            )
        )

    # ── D/F ratios (3 columns, fast mode only) ───────────────────
    if not full:
        for col, bl in BASELINE["cols"].items():
            DF = bl["DF"]
            params.append(
                Parameter(
                    name=f"{col}.DF",
                    distribution="normal",
                    params={"mu": DF, "sigma": 0.005},
                    bounds=(max(0.1, DF - 0.1), min(0.999, DF + 0.1)),
                    description=f"{col} distillate-to-feed ratio",
                )
            )

    # ── Feed flows (2 feeds) ─────────────────────────────────────
    for feed_name, bl in BASELINE["feeds"].items():
        F = bl["flow"]
        params.append(
            Parameter(
                name=f"feed.{feed_name}",
                distribution="normal",
                params={"mu": F, "sigma": 0.01 * F},
                bounds=(0.5 * F, 1.5 * F),
                description=f"{feed_name} feed flow (mol/h)",
            )
        )

    # ── Pressures (3 columns) ────────────────────────────────────
    for col, bl in BASELINE["cols"].items():
        P = bl["P"]
        params.append(
            Parameter(
                name=f"{col}.P",
                distribution="normal",
                params={"mu": P, "sigma": 1000.0},
                bounds=(80000.0, 110000.0),
                description=f"{col} pressure (Pa)",
            )
        )

    return ParameterSpace.from_list(params)


def _scale_stage(val: int, old_n: int, new_n: int) -> int:
    """Proportionally scale a 1-indexed stage position."""
    return max(2, min(new_n - 1, int(round(val * new_n / old_n))))


def make_build_fn(full: bool = False, n_stages: int | None = None):
    """Return a build_fn that maps a parameter vector to a FlowsheetConfig.

    In fast mode (full=False): no recycle streams, direct solve, single
    pass. This makes each solve ~0.6 s and suitable for UQ exploration.

    In full mode (full=True): full ISS-O topology with tear streams and
    Wegstein acceleration. ~17 s/solve.
    """

    base_config = load_flowsheet(FIXTURE_PATH)

    if n_stages is not None:
        # Scale column sizes
        for col in base_config.columns:
            old_n = col.n_stages
            col.n_stages = n_stages
            col.feed_positions = {
                k: _scale_stage(v, old_n, n_stages)
                for k, v in col.feed_positions.items()
            }

    if not full:
        # Remove recycle streams for fast mode
        base_config.tear_streams = []
        base_config.connections = [
            c
            for c in base_config.connections
            if c.from_unit not in ("CD2_bottom_recycle", "CD3_top")
        ]
        for col in base_config.columns:
            col.feed_positions = {
                k: v
                for k, v in col.feed_positions.items()
                if k not in ("CD2_bottom_recycle", "CD3_top")
            }

    param_names = build_parameter_space(full).names

    def build_fn(params: np.ndarray) -> FlowsheetConfig:
        config = copy.deepcopy(base_config)
        p = dict(zip(param_names, params))

        for col_cfg in config.columns:
            col = col_cfg.name
            if f"{col}.R" in p:
                col_cfg.reflux_ratio = p[f"{col}.R"]
            if f"{col}.DF" in p:
                col_cfg.distillate_to_feed = max(0.1, min(0.999, p[f"{col}.DF"]))
            if f"{col}.P" in p:
                col_cfg.pressure = p[f"{col}.P"]

        for feed_cfg in config.feeds:
            key = f"feed.{feed_cfg.name}"
            if key in p:
                feed_cfg.flow = p[key]

        return config

    return build_fn


def run_uq(
    full: bool = False,
    n_stages: int | None = None,
    sobol_n_base: int = 8,
    mc_n: int = 40,
    seed: int = 42,
    parallel: int = 1,
    output_dir: str = "uq_runs/isso",
):
    """Run ISS-O UQ study."""
    import h2iso.uq.runner as runner_mod

    space = build_parameter_space(full)
    build_fn = make_build_fn(full, n_stages)

    qoi_fn = qoi_isso_compact
    qoi_names = qoi_isso_compact_labels()

    # Patch runner to use flowsheet solver
    original_solve = runner_mod._solve_config
    runner_mod._solve_config = _solve_isso

    try:
        study = UQStudy(
            build_fn=build_fn,
            parameter_space=space,
            qoi_fn=qoi_fn,
            qoi_names=qoi_names,
        )

        mode = "full" if full else "fast"
        n_str = n_stages or (60 if full else 12)
        out = Path(output_dir) / f"{mode}_n{n_str}_seed{seed}"
        out.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Sobol screening ──────────────────────────────
        method = "wegstein" if full else "direct"
        n_iter = 50 if full else 1

        print(
            f"[Sobol] mode={mode}, n_base={sobol_n_base}, K={space.n_params}, "
            f"n_stages={n_str}"
        )
        sobol_result, sobol_summary = study.run_sobol(
            n_base=sobol_n_base,
            seed=seed,
            parallel=parallel,
            solve_kwargs={
                "method": method,
                "max_iter": n_iter,
                "continuation_substeps": 0 if not full else 3,
            },
        )

        print(
            f"  Converged: {sobol_summary.n_converged}/{sobol_summary.n_total} "
            f"(fail rate {sobol_summary.fail_rate:.1%})"
        )

        if sobol_result is not None:
            for j, qname in enumerate(sobol_result.qoi_names):
                top3 = sobol_result.top_k(k=3, qoi_index=j)
                print(f"  Top-3 for {qname}: {', '.join(top3)}")
        else:
            print("  [WARNING] Sobol skipped (insufficient converged)")

        # ── Step 2: LHS Monte Carlo ──────────────────────────────
        print(f"[MC] mode={mode}, n={mc_n}, n_stages={n_str}")
        mc_summary = study.run_monte_carlo(
            n=mc_n,
            seed=seed,
            parallel=parallel,
            solve_kwargs={
                "method": method,
                "max_iter": n_iter,
                "continuation_substeps": 0 if not full else 3,
            },
        )

        print(
            f"  Converged: {mc_summary.n_converged}/{mc_summary.n_total} "
            f"(fail rate {mc_summary.fail_rate:.1%})"
        )

        if mc_summary.n_converged > 0:
            qmat = mc_summary.qoi_matrix
            for j, qname in enumerate(study.qoi_names):
                col = qmat[:, j]
                mean = col.mean()
                std = col.std()
                lo = np.percentile(col, 2.5)
                hi = np.percentile(col, 97.5)
                print(
                    f"  {qname}: mean={mean:.5g}, std={std:.4g}, "
                    f"95% CI=[{lo:.4g}, {hi:.4g}]"
                )

        report_path = study.save(
            mc_summary,
            out / "mc",
            sobol_result=sobol_result,
            title=f"ISS-O UQ Report ({mode} mode, n_stages={n_str})",
        )
        print(f"\nReport saved to: {report_path}")

    finally:
        runner_mod._solve_config = original_solve

    return sobol_result, sobol_summary, mc_summary


def _solve_isso(config, **kwargs):
    """Solve an ISS-O FlowsheetConfig."""
    solver = SequentialModularSolver(
        config,
        method=kwargs.pop("method", "direct"),
        continuation_substeps=kwargs.pop("continuation_substeps", 0),
        on_unit_failure=kwargs.pop("on_unit_failure", "raise"),
    )
    return solver.solve(
        max_iter=kwargs.pop("max_iter", 1),
        tol=kwargs.pop("tol", 1e-4),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run ISS-O flowsheet UQ validation study"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full ISS-O with recycles (default: fast no-recycle mode)",
    )
    parser.add_argument(
        "--sobol-n",
        type=int,
        default=None,
        help="Sobol base sample count (default: 16 for fast, 32 for full)",
    )
    parser.add_argument(
        "--mc-n",
        type=int,
        default=None,
        help="MC sample count (default: 100 for fast, 500 for full)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        default="uq_runs/isso",
    )
    args = parser.parse_args()

    full = args.full
    sobol_n = args.sobol_n or (32 if full else 16)
    mc_n = args.mc_n or (500 if full else 100)
    n_stages = None  # defaults to 60/70/60 for full, 12 for fast

    run_uq(
        full=full,
        n_stages=n_stages,
        sobol_n_base=sobol_n,
        mc_n=mc_n,
        seed=args.seed,
        parallel=args.parallel,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
