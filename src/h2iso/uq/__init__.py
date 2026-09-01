"""h2iso UQ — Uncertainty propagation framework.

Usage
-----
::

    from h2iso.uq import UQStudy, ParameterSpace, qoi_default

    space = ParameterSpace.from_list([
        Parameter("reflux_ratio", "normal", {"mu": 15, "sigma": 0.3}),
        Parameter("feed_flow", "normal", {"mu": 80.357, "sigma": 0.8}),
    ])

    study = UQStudy(
        build_fn=my_build_fn,     # maps np.ndarray -> ColumnSpec/FlowsheetConfig
        parameter_space=space,
        qoi_fn=qoi_default,
    )

    # Step 1: Sobol screening
    sobol = study.run_sobol(n_base=64, seed=42)

    # Step 2: LHS Monte Carlo on top-K parameters
    mc = study.run_monte_carlo(n=500, seed=42, parallel=4)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from h2iso.uq.distributions import Parameter
from h2iso.uq.qoi import qoi_default, qoi_labels
from h2iso.uq.report import save_report
from h2iso.uq.runner import RunSummary, run_samples
from h2iso.uq.sampler import lhs_sample, random_sample, sobol_sample
from h2iso.uq.sobol import SobolResult, analyze_sobol

__all__ = [
    "Parameter",
    "ParameterSpace",
    "UQStudy",
    "RunSummary",
    "SobolResult",
    "qoi_default",
    "qoi_labels",
]


@dataclass
class ParameterSpace:
    """Container for a set of uncertain parameters."""

    parameters: list[Parameter] = field(default_factory=list)

    @classmethod
    def from_list(cls, params: list[Parameter]) -> ParameterSpace:
        return cls(parameters=list(params))

    @classmethod
    def from_dicts(cls, dicts: list[dict]) -> ParameterSpace:
        return cls(parameters=[Parameter.from_dict(d) for d in dicts])

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.parameters]

    @property
    def n_params(self) -> int:
        return len(self.parameters)

    def to_dict(self) -> dict:
        return {"parameters": [p.to_dict() for p in self.parameters]}


@dataclass
class UQStudy:
    """Orchestrates a UQ propagation study.

    Parameters
    ----------
    build_fn : callable
        ``build_fn(parameter_values: ndarray) -> config`` where *config*
        is either a :class:`~h2iso.flowsheet.schema.FlowsheetConfig` or
        a :class:`~h2iso.mesh.column.ColumnSpec`.
    parameter_space : ParameterSpace
    qoi_fn : callable or None
        Defaults to :func:`qoi_default`.
    qoi_names : list[str] or None
        Labels for the QoI vector. Auto-generated if ``None``.
    """

    build_fn: Callable
    parameter_space: ParameterSpace
    qoi_fn: Callable | None = None
    qoi_names: list[str] | None = None

    def __post_init__(self) -> None:
        if self.qoi_fn is None:
            self.qoi_fn = qoi_default
        if self.qoi_names is None:
            self.qoi_names = qoi_labels()

    def run_sobol(
        self,
        n_base: int = 128,
        seed: int | None = None,
        parallel: int = 1,
        timeout: float | None = None,
        solve_kwargs: dict | None = None,
    ) -> tuple[SobolResult, RunSummary]:
        """Run Sobol sensitivity screening.

        Returns
        -------
        (SobolResult, RunSummary)
        """
        samples = sobol_sample(
            self.parameter_space.parameters,
            n_base=n_base,
            seed=seed,
        )
        summary = run_samples(
            samples,
            self.build_fn,
            qoi_fn=self.qoi_fn,
            parallel=parallel,
            timeout=timeout,
            solve_kwargs=solve_kwargs,
            param_names=self.parameter_space.names,
        )

        if summary.fail_rate > 0.05:
            import warnings

            warnings.warn(
                f"Sobol run fail rate {summary.fail_rate:.1%} > 5%. "
                "Sobol analysis requires the full sample matrix; "
                "consider robustifying the solver before proceeding.",
                stacklevel=2,
            )

        qmat = summary.qoi_matrix
        smat = summary.sample_matrix_converged
        sobol_result = (
            analyze_sobol(
                self.parameter_space.parameters,
                smat,
                qmat,
                qoi_names=self.qoi_names,
                n_base=n_base,
                seed=seed,
            )
            if qmat.size > 0
            else None
        )

        return sobol_result, summary

    def run_monte_carlo(
        self,
        n: int = 1000,
        seed: int | None = None,
        parallel: int = 1,
        timeout: float | None = None,
        solve_kwargs: dict | None = None,
        parameters: list[Parameter] | None = None,
    ) -> RunSummary:
        """Run LHS Monte Carlo.

        If *parameters* is given (e.g. a top-K subset from Sobol),
        only those parameters are sampled; the rest use their mean values.
        """
        params = (
            parameters if parameters is not None else self.parameter_space.parameters
        )
        samples = lhs_sample(params, n=n, seed=seed)

        # If a subset was used, expand the sample matrix to full size
        if parameters is not None and len(parameters) < self.parameter_space.n_params:
            full_samples = np.tile(
                np.array([p.mean() for p in self.parameter_space.parameters]),
                (n, 1),
            )
            # Map sub-parameter indices to full-parameter indices
            for j, sub_p in enumerate(parameters):
                full_j = self.parameter_space.names.index(sub_p)
                full_samples[:, full_j] = samples[:, j]
            samples = full_samples

        return run_samples(
            samples,
            self.build_fn,
            qoi_fn=self.qoi_fn,
            parallel=parallel,
            timeout=timeout,
            solve_kwargs=solve_kwargs,
            param_names=self.parameter_space.names,
        )

    def run_random(
        self,
        n: int = 1000,
        seed: int | None = None,
        parallel: int = 1,
        timeout: float | None = None,
        solve_kwargs: dict | None = None,
    ) -> RunSummary:
        """Plain iid Monte-Carlo sampling."""
        samples = random_sample(
            self.parameter_space.parameters,
            n=n,
            seed=seed,
        )
        return run_samples(
            samples,
            self.build_fn,
            qoi_fn=self.qoi_fn,
            parallel=parallel,
            timeout=timeout,
            solve_kwargs=solve_kwargs,
            param_names=self.parameter_space.names,
        )

    def save(
        self,
        summary: RunSummary,
        output_dir: str | Path,
        sobol_result: SobolResult | None = None,
        title: str = "UQ Study Report",
    ) -> Path:
        """Write report + CSV + failures to *output_dir*."""
        return save_report(
            summary,
            self.parameter_space.names,
            self.qoi_names,
            output_dir,
            sobol_result=sobol_result,
            title=title,
        )
