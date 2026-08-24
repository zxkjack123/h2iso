"""CD2 UQ validation case — Sobol screening + Monte Carlo on Wang 2022 ISS-I CD2.

This script runs a complete UQ propagation study on the CD2 distillation
column (Wang et al. 2022, ISS-I) using the h2iso UQ framework.

Parameters perturbed (operational subset, P06-P09 from uq_propagation_plan.md):
  - P06: reflux ratio R (Normal, σ=2% × baseline)
  - P07: feed flow F (Normal, σ=1% × baseline)
  - P08: feed composition z_D2 (Dirichlet-like via two normals)
  - P09: operating pressure P (Normal, σ=0.5 kPa)

Usage:
    python -m h2iso.uq.run_cd2          # 15-stage fast run (testing)
    python -m h2iso.uq.run_cd2 --full    # 75-stage canonical run (publication)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from h2iso.mesh.column import Column, ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver
from h2iso.uq import (
    Parameter,
    ParameterSpace,
    UQStudy,
    qoi_default,
    qoi_labels,
)
from h2iso.uq.runner import _is_converged

# ── Baseline CD2 parameters (Wang 2022 Table 1 + Table 5) ──────────

BASELINE = {
    "n_stages": 75,
    "feed_stage": 37,
    "feed_flow": 80.357,  # mol/h
    "z_D2": 0.98,
    "z_DT": 0.02,
    "pressure": 95000.0,  # Pa (avg of 90k/100k)
    "reflux_ratio": 15.0,
    "distillate_to_feed": 0.979,
}


def build_parameter_space() -> ParameterSpace:
    """Define the UQ parameter space for CD2 operational perturbations."""
    R = BASELINE["reflux_ratio"]
    F = BASELINE["feed_flow"]
    z_D2 = BASELINE["z_D2"]
    P = BASELINE["pressure"]

    return ParameterSpace.from_list(
        [
            Parameter(
                name="reflux_ratio",
                distribution="normal",
                params={"mu": R, "sigma": 0.02 * R},
                bounds=(0.5 * R, 2.0 * R),
                description="Reflux ratio (P06, σ=2% × baseline)",
            ),
            Parameter(
                name="feed_flow",
                distribution="normal",
                params={"mu": F, "sigma": 0.01 * F},
                bounds=(0.5 * F, 1.5 * F),
                description="Feed flow rate (P07, σ=1% × baseline)",
            ),
            Parameter(
                name="z_D2",
                distribution="normal",
                params={"mu": z_D2, "sigma": 0.05 * z_D2},
                bounds=(0.5, 0.999),
                description="Feed D2 mole fraction (P08, cv=5%)",
            ),
            Parameter(
                name="pressure",
                distribution="normal",
                params={"mu": P, "sigma": 500.0},
                bounds=(80000.0, 110000.0),
                description="Column pressure (P09, σ=0.5 kPa)",
            ),
        ]
    )


def make_build_fn(n_stages: int = 75, use_continuation: bool = True):
    """Return a build_fn that maps a parameter vector to a solved column.

    For n_stages <= 15, solves directly without continuation (fast).
    For n_stages > 15, uses continuation from 15 → target.
    """

    def build_fn(params: np.ndarray):
        R, F, z_D2, P = params

        # Construct feed composition from z_D2 and z_DT (= 1 - z_D2)
        z_DT = max(1e-6, 1.0 - z_D2)
        z_D2 = max(1e-6, z_D2)
        total = z_D2 + z_DT
        z_D2 /= total
        z_DT /= total
        z = np.array([0, 0, 0, z_D2, z_DT, 0])

        if n_stages <= 15 and not use_continuation:
            return ColumnSpec(
                n_stages=n_stages,
                feed_stage=max(2, n_stages // 2),
                feed_flow=F,
                feed_composition=z,
                pressure=P,
                reflux_ratio=R,
                distillate_to_feed=BASELINE["distillate_to_feed"],
            )

        # For continuation, return a base spec + continuation config
        # We use a wrapper object that _solve_config can dispatch on
        base_spec = ColumnSpec(
            n_stages=15,
            feed_stage=8,
            feed_flow=F,
            feed_composition=z,
            pressure=P,
            reflux_ratio=R,
            distillate_to_feed=BASELINE["distillate_to_feed"],
        )
        return _CD2ContinuationConfig(base_spec, n_stages)

    return build_fn


class _CD2ContinuationConfig:
    """Wrapper that tells the UQ runner to use continuation for this column."""

    def __init__(self, base_spec: ColumnSpec, target_n: int):
        self.base_spec = base_spec
        self.target_n = target_n


def _solve_cd2(config, **kwargs):
    """Custom solve dispatcher for CD2 with continuation support."""
    if isinstance(config, _CD2ContinuationConfig):
        solver = ContinuationSolver()
        if config.target_n > 30:
            solver.add_step("N", target=30, n_substeps=1)
        substeps = max(1, (config.target_n - 30) // 15)
        solver.add_step("N", target=config.target_n, n_substeps=substeps)
        result = solver.solve(config.base_spec)
        return result.final
    if isinstance(config, ColumnSpec):
        col = Column(config)
        return col.solve()
    raise TypeError(f"Unsupported config type: {type(config).__name__}")


def run_uq(
    n_stages: int = 15,
    sobol_n_base: int = 32,
    mc_n: int = 200,
    seed: int = 42,
    parallel: int = 1,
    output_dir: str = "uq_runs/cd2",
):
    """Run the CD2 UQ study and save results.

    Parameters
    ----------
    n_stages : int
        Column size. 15 for fast testing, 75 for canonical validation.
    sobol_n_base : int
        Base sample count for Sobol screening.
    mc_n : int
        Number of LHS Monte Carlo samples.
    seed : int
        Random seed for reproducibility.
    parallel : int
        Number of worker processes (1 = serial).
    output_dir : str
        Where to write report files.
    """
    import h2iso.uq.runner as runner_mod

    # Patch the solver dispatcher
    runner_mod._solve_config = _solve_cd2
    runner_mod._is_converged = _is_converged

    space = build_parameter_space()
    use_cont = n_stages > 15

    study = UQStudy(
        build_fn=make_build_fn(n_stages=n_stages, use_continuation=use_cont),
        parameter_space=space,
        qoi_fn=qoi_default,
        qoi_names=qoi_labels("CD2"),
    )

    out = Path(output_dir) / f"n{n_stages}_seed{seed}"
    out.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Sobol screening ──────────────────────────────────
    print(f"[Sobol] n_base={sobol_n_base}, K={space.n_params}, n_stages={n_stages} ...")
    sobol_result, sobol_summary = study.run_sobol(
        n_base=sobol_n_base,
        seed=seed,
        parallel=parallel,
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
        print("  [WARNING] Sobol analysis skipped (insufficient converged samples)")

    # ── Step 2: LHS Monte Carlo ──────────────────────────────────
    print(f"[MC] n={mc_n}, n_stages={n_stages} ...")
    mc_summary = study.run_monte_carlo(
        n=mc_n,
        seed=seed,
        parallel=parallel,
    )

    print(
        f"  Converged: {mc_summary.n_converged}/{mc_summary.n_total} "
        f"(fail rate {mc_summary.fail_rate:.1%})"
    )

    if mc_summary.n_converged > 0:
        qmat = mc_summary.qoi_matrix
        for j, qname in enumerate(study.qoi_names):
            mean = qmat[:, j].mean()
            std = qmat[:, j].std()
            lo = np.percentile(qmat[:, j], 2.5)
            hi = np.percentile(qmat[:, j], 97.5)
            print(
                f"  {qname}: mean={mean:.6g}, std={std:.4g}, "
                f"95% CI=[{lo:.6g}, {hi:.6g}]"
            )

    # ── Save report ──────────────────────────────────────────────
    report_path = study.save(
        mc_summary,
        out / "mc",
        sobol_result=sobol_result,
        title=f"CD2 UQ Report (N={n_stages}, MC n={mc_n})",
    )
    print(f"\nReport saved to: {report_path}")

    return sobol_result, sobol_summary, mc_summary


def main():
    parser = argparse.ArgumentParser(description="Run CD2 UQ validation study")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Use 75-stage column (default: 15-stage for fast testing)",
    )
    parser.add_argument(
        "--sobol-n",
        type=int,
        default=None,
        help="Sobol base sample count (default: 32 for fast, 64 for full)",
    )
    parser.add_argument(
        "--mc-n",
        type=int,
        default=None,
        help="MC sample count (default: 200 for fast, 2000 for full)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        default="uq_runs/cd2",
        help="Output directory (default: uq_runs/cd2)",
    )
    args = parser.parse_args()

    n_stages = 75 if args.full else 15
    sobol_n = args.sobol_n or (64 if args.full else 32)
    mc_n = args.mc_n or (2000 if args.full else 200)

    run_uq(
        n_stages=n_stages,
        sobol_n_base=sobol_n,
        mc_n=mc_n,
        seed=args.seed,
        parallel=args.parallel,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
