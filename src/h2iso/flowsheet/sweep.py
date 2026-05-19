"""Parameter sweep for flowsheet design optimization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from h2iso.flowsheet.schema import FlowsheetConfig
from h2iso.flowsheet.solver import FlowsheetResult, SequentialModularSolver


@dataclass
class SweepPoint:
    """Result from a single sweep point."""

    parameters: dict[str, float]
    result: FlowsheetResult | None
    converged: bool
    error: str | None = None


@dataclass
class SweepResult:
    """Collection of sweep results."""

    parameter_name: str
    parameter_values: list[float]
    points: list[SweepPoint] = field(default_factory=list)

    @property
    def converged_points(self) -> list[SweepPoint]:
        """Return only converged sweep points."""
        return [p for p in self.points if p.converged]

    def to_dict(self) -> dict:
        """Export sweep results as serializable dict."""
        records = []
        for pt in self.points:
            record = {
                "parameters": pt.parameters,
                "converged": pt.converged,
                "error": pt.error,
            }
            if pt.result is not None:
                record["iterations"] = pt.result.iterations
                record["tear_residual"] = float(pt.result.tear_residual)
                # Add stream summaries
                record["streams"] = {}
                for name, stream in pt.result.streams.items():
                    if name.endswith("_distillate") or name.endswith("_bottoms"):
                        record["streams"][name] = {
                            "flow_mol_h": float(stream.flow),
                            "temperature_K": float(stream.temperature),
                            "composition": [float(x) for x in stream.composition],
                        }
            records.append(record)
        return {
            "parameter_name": self.parameter_name,
            "parameter_values": self.parameter_values,
            "n_converged": len(self.converged_points),
            "n_total": len(self.points),
            "results": records,
        }

    def to_json(self, path: str | Path) -> None:
        """Export to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class ParameterSweep:
    """Sweep design parameters over a flowsheet.

    Parameters
    ----------
    config : FlowsheetConfig
        Base flowsheet configuration.
    target_column : str
        Column name to vary parameters on.
    continuation_substeps : int
        Continuation substeps for column solving.
    method : str
        Convergence method for tear streams.
    """

    def __init__(
        self,
        config: FlowsheetConfig,
        target_column: str,
        continuation_substeps: int = 3,
        method: str = "wegstein",
    ):
        self.base_config = config
        self.target_column = target_column
        self.continuation_substeps = continuation_substeps
        self.method = method

    def sweep_reflux_ratio(
        self,
        values: list[float],
        max_iter: int = 50,
        tol: float = 1e-4,
    ) -> SweepResult:
        """Sweep reflux ratio for target column.

        Parameters
        ----------
        values : list[float]
            Reflux ratio values to evaluate.
        max_iter : int
            Max iterations per solve.
        tol : float
            Convergence tolerance.

        Returns
        -------
        SweepResult
        """
        return self._sweep("reflux_ratio", values, max_iter, tol)

    def sweep_n_stages(
        self,
        values: list[int],
        max_iter: int = 50,
        tol: float = 1e-4,
    ) -> SweepResult:
        """Sweep number of stages for target column."""
        return self._sweep("n_stages", [int(v) for v in values], max_iter, tol)

    def sweep_distillate_to_feed(
        self,
        values: list[float],
        max_iter: int = 50,
        tol: float = 1e-4,
    ) -> SweepResult:
        """Sweep D/F ratio for target column."""
        return self._sweep("distillate_to_feed", values, max_iter, tol)

    def _sweep(
        self,
        param_name: str,
        values: list,
        max_iter: int,
        tol: float,
    ) -> SweepResult:
        """Generic parameter sweep."""
        result = SweepResult(
            parameter_name=param_name,
            parameter_values=values,
        )

        for val in values:
            # Create modified config
            config = self._modify_config(param_name, val)
            params = {param_name: val}

            try:
                solver = SequentialModularSolver(
                    config,
                    method=self.method,
                    continuation_substeps=self.continuation_substeps,
                )
                solve_result = solver.solve(max_iter=max_iter, tol=tol)
                result.points.append(SweepPoint(
                    parameters=params,
                    result=solve_result,
                    converged=solve_result.converged,
                ))
            except Exception as e:
                result.points.append(SweepPoint(
                    parameters=params,
                    result=None,
                    converged=False,
                    error=str(e),
                ))

        return result

    def _modify_config(self, param_name: str, value) -> FlowsheetConfig:
        """Create a copy of config with one parameter modified."""
        import copy
        config = copy.deepcopy(self.base_config)

        # Find target column
        for col in config.columns:
            if col.name == self.target_column:
                if param_name == "reflux_ratio":
                    col.reflux_ratio = value
                elif param_name == "n_stages":
                    col.n_stages = int(value)
                    # Scale feed positions proportionally
                    old_n = next(
                        c.n_stages for c in self.base_config.columns
                        if c.name == self.target_column
                    )
                    scale = int(value) / old_n
                    col.feed_positions = {
                        k: max(2, min(int(value) - 1, int(v * scale)))
                        for k, v in col.feed_positions.items()
                    }
                elif param_name == "distillate_to_feed":
                    col.distillate_to_feed = value
                break

        return config
