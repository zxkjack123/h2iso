"""Parallel runner: evaluate flowsheet.solve() across a sample matrix.

Each row of the sample matrix is a vector of parameter values that the
``apply_fn`` callback maps to a concrete configuration before solving.
The runner handles:

- Parallel execution via ``concurrent.futures.ProcessPoolExecutor``.
- Per-sample timeout and exception capture (failures are recorded, not raised).
- Deterministic ordering of results to match the input rows.
"""

from __future__ import annotations

import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from h2iso.uq.qoi import qoi_default


@dataclass
class RunResult:
    """Outcome of a single UQ sample evaluation."""

    sample_index: int
    parameter_values: np.ndarray
    qoi_values: np.ndarray | None
    converged: bool
    error: str | None = None


@dataclass
class RunSummary:
    """Aggregated results from a full UQ run."""

    results: list[RunResult] = field(default_factory=list)
    n_total: int = 0
    n_converged: int = 0
    n_failed: int = 0
    fail_rate: float = 0.0

    @property
    def qoi_matrix(self) -> np.ndarray:
        """Matrix of converged QoI values, shape (n_converged, n_qoi)."""
        rows = [r.qoi_values for r in self.results if r.qoi_values is not None]
        if not rows:
            return np.empty((0, 0))
        return np.vstack(rows)

    @property
    def sample_matrix_converged(self) -> np.ndarray:
        """Sample rows that converged, shape (n_converged, K)."""
        rows = [r.parameter_values for r in self.results if r.qoi_values is not None]
        if not rows:
            return np.empty((0, 0))
        return np.vstack(rows)


def _is_converged(result) -> bool:
    """Check convergence for both FlowsheetResult and ColumnResult."""
    if hasattr(result, "converged"):
        return result.converged
    # ColumnResult: check convergence_info["success"]
    info = getattr(result, "convergence_info", {})
    return info.get("success", False)


def _run_single(
    sample_index: int,
    parameter_values: np.ndarray,
    build_fn: Callable,
    qoi_fn: Callable,
    solve_kwargs: dict | None,
    param_names: list[str] | None = None,
) -> RunResult:
    """Worker function executed in a subprocess."""
    try:
        from h2iso.uq.properties import property_override, resolve_property_params

        solve_kwargs = solve_kwargs or {}
        config = build_fn(parameter_values)

        # Apply property overrides if any param names start with "souers." or "bip."
        overrides = {}
        if param_names is not None:
            overrides = resolve_property_params(parameter_values, param_names)

        with property_override(overrides):
            result = _solve_config(config, **solve_kwargs)
        if not _is_converged(result):
            return RunResult(
                sample_index=sample_index,
                parameter_values=parameter_values,
                qoi_values=None,
                converged=False,
                error="Flowsheet did not converge",
            )
        qoi_vec = qoi_fn(result)
        return RunResult(
            sample_index=sample_index,
            parameter_values=parameter_values,
            qoi_values=qoi_vec,
            converged=True,
        )
    except Exception as exc:
        tb = traceback.format_exc()
        return RunResult(
            sample_index=sample_index,
            parameter_values=parameter_values,
            qoi_values=None,
            converged=False,
            error=f"{type(exc).__name__}: {exc}\n{tb}",
        )


def _solve_config(config, **kwargs):
    """Dispatch to the correct solver based on config type."""
    # Local import to avoid circular deps / optional CasADi at module load
    from h2iso.flowsheet.schema import FlowsheetConfig
    from h2iso.flowsheet.solver import SequentialModularSolver
    from h2iso.mesh.column import Column, ColumnSpec

    if isinstance(config, FlowsheetConfig):
        solver = SequentialModularSolver(
            config,
            method=kwargs.pop("method", "wegstein"),
            continuation_substeps=kwargs.pop("continuation_substeps", 3),
            on_unit_failure=kwargs.pop("on_unit_failure", "raise"),
        )
        return solver.solve(
            max_iter=kwargs.pop("max_iter", 50),
            tol=kwargs.pop("tol", 1e-4),
        )
    if isinstance(config, ColumnSpec):
        col = Column(config)
        return col.solve()
    raise TypeError(f"Unsupported config type: {type(config).__name__}")


def run_samples(
    sample_matrix: np.ndarray,
    build_fn: Callable,
    qoi_fn: Callable | None = None,
    parallel: int = 1,
    timeout: float | None = None,
    solve_kwargs: dict | None = None,
    param_names: list[str] | None = None,
) -> RunSummary:
    """Evaluate a sample matrix.

    Parameters
    ----------
    sample_matrix : ndarray of shape (N, K)
        Each row is a vector of parameter values.
    build_fn : callable
        ``build_fn(parameter_values) -> config``: maps a parameter vector to
        either a :class:`FlowsheetConfig` or a :class:`ColumnSpec`.
    qoi_fn : callable or None
        ``qoi_fn(result) -> ndarray``. Defaults to :func:`h2iso.uq.qoi.qoi_default`.
    parallel : int
        Number of worker processes. ``1`` = serial (useful for debugging).
    timeout : float or None
        Per-sample wall-clock timeout in seconds (ignored when ``parallel == 1``).
    solve_kwargs : dict or None
        Extra keyword arguments forwarded to the solver (e.g. ``max_iter``).
    param_names : list[str] or None
        Parameter names. When provided, parameters matching ``"souers.*"`` or
        ``"bip.*"`` are applied as global property overrides during each solve.

    Returns
    -------
    RunSummary
    """
    if qoi_fn is None:
        qoi_fn = qoi_default
    solve_kwargs = solve_kwargs or {}

    N = sample_matrix.shape[0]
    results: list[RunResult | None] = [None] * N

    if parallel <= 1:
        for i in range(N):
            results[i] = _run_single(
                i, sample_matrix[i], build_fn, qoi_fn, solve_kwargs, param_names
            )
    else:
        ctx = "spawn" if sys.platform == "win32" else "fork"
        with ProcessPoolExecutor(
            max_workers=parallel,
            mp_context=__import__(
                "multiprocessing", fromlist=["get_context"]
            ).get_context(ctx),
        ) as pool:
            futures = {}
            for i in range(N):
                fut = pool.submit(
                    _run_single,
                    i,
                    sample_matrix[i],
                    build_fn,
                    qoi_fn,
                    solve_kwargs,
                    param_names,
                )
                futures[fut] = i

            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    results[idx] = fut.result(timeout=timeout)
                except Exception as exc:
                    results[idx] = RunResult(
                        sample_index=idx,
                        parameter_values=sample_matrix[idx],
                        qoi_values=None,
                        converged=False,
                        error=f"Worker error: {exc}",
                    )

    summary = RunSummary(n_total=N)
    for r in results:
        if r is None:
            continue
        summary.results.append(r)
        if r.converged:
            summary.n_converged += 1
        else:
            summary.n_failed += 1
    summary.fail_rate = summary.n_failed / summary.n_total if summary.n_total else 0.0
    return summary
