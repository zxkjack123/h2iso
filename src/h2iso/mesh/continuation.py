"""Continuation solver for high-stage-count distillation columns.

Implements a staged continuation strategy to solve columns with many
theoretical stages by progressively increasing N from a small (easy-to-solve)
column to the target size.

Strategy:
1. Solve small column (e.g., N=15)
2. Interpolate solution profile to larger N
3. Use interpolated profile as warm start
4. Adaptive step size: halve on failure, restore on success
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from h2iso.mesh.column import Column, ColumnResult, ColumnSpec


@dataclass
class ContinuationStep:
    """A single continuation step."""

    param: str  # "N", "R", "D_F", "feed"
    target: float | np.ndarray
    n_substeps: int = 1


@dataclass
class ContinuationResult:
    """Result from continuation solve, including intermediate steps."""

    final: ColumnResult
    steps_taken: int
    step_history: list[dict] = field(default_factory=list)


class ContinuationSolver:
    """Staged continuation solver for difficult column problems."""

    def __init__(self, max_retries_per_step: int = 3):
        self.steps: list[ContinuationStep] = []
        self.max_retries = max_retries_per_step

    def add_step(self, param: str, target: float | np.ndarray, n_substeps: int = 1):
        """Add a continuation step.

        Parameters
        ----------
        param : str
            Parameter to vary: "N", "R", "D_F", "feed"
        target : float or ndarray
            Target value for the parameter
        n_substeps : int
            Number of sub-steps to reach the target
        """
        self.steps.append(ContinuationStep(param=param, target=target, n_substeps=n_substeps))

    def solve(self, base_spec: ColumnSpec) -> ContinuationResult:
        """Execute continuation from base_spec through all added steps.

        Parameters
        ----------
        base_spec : ColumnSpec
            Initial column specification to start from.

        Returns
        -------
        ContinuationResult
        """
        # Solve base column first
        col = Column(base_spec)
        result = col.solve()
        if not result.convergence_info["success"]:
            raise RuntimeError(
                f"Base column solve failed: {result.convergence_info['status']}"
            )

        current_spec = base_spec
        step_history = [{"param": "base", "value": base_spec.n_stages, "success": True}]
        total_steps = 0

        for step in self.steps:
            result, current_spec, history = self._execute_step(
                step, current_spec, result
            )
            step_history.extend(history)
            total_steps += len(history)

        return ContinuationResult(
            final=result,
            steps_taken=total_steps,
            step_history=step_history,
        )

    def _execute_step(
        self,
        step: ContinuationStep,
        current_spec: ColumnSpec,
        current_result: ColumnResult,
    ) -> tuple[ColumnResult, ColumnSpec, list[dict]]:
        """Execute a single continuation step with adaptive sub-stepping."""
        history = []

        if step.param == "N":
            return self._continue_N(step, current_spec, current_result, history)
        elif step.param == "R":
            return self._continue_R(step, current_spec, current_result, history)
        elif step.param == "D_F":
            return self._continue_DF(step, current_spec, current_result, history)
        else:
            raise ValueError(f"Unknown continuation parameter: {step.param}")

    def _continue_N(
        self,
        step: ContinuationStep,
        spec: ColumnSpec,
        result: ColumnResult,
        history: list[dict],
    ) -> tuple[ColumnResult, ColumnSpec, list[dict]]:
        """Continuation in number of stages."""
        N_start = spec.n_stages
        N_target = int(step.target)
        n_sub = step.n_substeps

        # Generate sub-step sizes
        N_values = np.linspace(N_start, N_target, n_sub + 1, dtype=int)[1:]
        # Remove duplicates
        N_values = sorted(set(N_values))
        if N_values[-1] != N_target:
            N_values.append(N_target)

        current_result = result
        current_spec = spec

        for N_next in N_values:
            # Adjust feed stage proportionally
            feed_frac = spec.feed_stage / spec.n_stages
            new_feed = max(2, min(N_next - 1, int(round(feed_frac * N_next))))

            new_spec = ColumnSpec(
                n_stages=N_next,
                feed_stage=new_feed,
                feed_flow=spec.feed_flow,
                feed_composition=spec.feed_composition.copy(),
                pressure=spec.pressure,
                reflux_ratio=spec.reflux_ratio,
                distillate_to_feed=spec.distillate_to_feed,
                feed_quality=spec.feed_quality,
            )

            # Interpolate solution as initial guess
            x0 = self._interpolate_profile(current_result, N_next)

            # Try solve with adaptive retry
            success = False
            for attempt in range(self.max_retries + 1):
                col = Column(new_spec)
                new_result = col.solve(x0=x0)
                if new_result.convergence_info["success"]:
                    success = True
                    break
                # Adaptive: perturb initial guess slightly
                x0 = x0 * (1 + 0.01 * np.random.randn(len(x0)))
                x0 = np.clip(x0, 0.0, None)

            history.append({
                "param": "N",
                "value": N_next,
                "success": success,
                "iterations": new_result.convergence_info.get("iterations", -1),
            })

            if not success:
                raise RuntimeError(
                    f"Continuation failed at N={N_next}: "
                    f"{new_result.convergence_info['status']}"
                )

            current_result = new_result
            current_spec = new_spec

        return current_result, current_spec, history

    def _continue_R(
        self,
        step: ContinuationStep,
        spec: ColumnSpec,
        result: ColumnResult,
        history: list[dict],
    ) -> tuple[ColumnResult, ColumnSpec, list[dict]]:
        """Continuation in reflux ratio."""
        R_start = spec.reflux_ratio
        R_target = float(step.target)
        n_sub = step.n_substeps

        R_values = np.linspace(R_start, R_target, n_sub + 1)[1:]
        current_result = result
        current_spec = spec

        for R_next in R_values:
            new_spec = ColumnSpec(
                n_stages=spec.n_stages,
                feed_stage=spec.feed_stage,
                feed_flow=spec.feed_flow,
                feed_composition=spec.feed_composition.copy(),
                pressure=spec.pressure,
                reflux_ratio=R_next,
                distillate_to_feed=spec.distillate_to_feed,
                feed_quality=spec.feed_quality,
            )

            # Use current solution as warm start (same N, different R)
            x0 = self._result_to_x0(current_result)

            col = Column(new_spec)
            new_result = col.solve(x0=x0)

            success = new_result.convergence_info["success"]
            history.append({"param": "R", "value": R_next, "success": success})

            if not success:
                raise RuntimeError(
                    f"Continuation failed at R={R_next:.2f}: "
                    f"{new_result.convergence_info['status']}"
                )

            current_result = new_result
            current_spec = new_spec

        return current_result, current_spec, history

    def _continue_DF(
        self,
        step: ContinuationStep,
        spec: ColumnSpec,
        result: ColumnResult,
        history: list[dict],
    ) -> tuple[ColumnResult, ColumnSpec, list[dict]]:
        """Continuation in D/F ratio."""
        DF_start = spec.distillate_to_feed
        DF_target = float(step.target)
        n_sub = step.n_substeps

        DF_values = np.linspace(DF_start, DF_target, n_sub + 1)[1:]
        current_result = result
        current_spec = spec

        for DF_next in DF_values:
            new_spec = ColumnSpec(
                n_stages=spec.n_stages,
                feed_stage=spec.feed_stage,
                feed_flow=spec.feed_flow,
                feed_composition=spec.feed_composition.copy(),
                pressure=spec.pressure,
                reflux_ratio=spec.reflux_ratio,
                distillate_to_feed=DF_next,
                feed_quality=spec.feed_quality,
            )

            x0 = self._result_to_x0(current_result)

            col = Column(new_spec)
            new_result = col.solve(x0=x0)

            success = new_result.convergence_info["success"]
            history.append({"param": "D_F", "value": DF_next, "success": success})

            if not success:
                raise RuntimeError(
                    f"Continuation failed at D/F={DF_next:.3f}: "
                    f"{new_result.convergence_info['status']}"
                )

            current_result = new_result
            current_spec = new_spec

        return current_result, current_spec, history

    def _interpolate_profile(self, result: ColumnResult, N_new: int) -> np.ndarray:
        """Interpolate a column result to a different number of stages.

        Maps old stage positions [0, 1, ..., N_old-1] to new positions [0, 1, ..., N_new-1]
        using linear interpolation.
        """
        N_old = len(result.T_profile)
        Nc = result.x_profile.shape[1]

        # Normalized stage positions
        pos_old = np.linspace(0, 1, N_old)
        pos_new = np.linspace(0, 1, N_new)

        # Interpolate each variable
        T_new = np.interp(pos_new, pos_old, result.T_profile)
        x_new = np.zeros((N_new, Nc))
        y_new = np.zeros((N_new, Nc))
        for i in range(Nc):
            x_new[:, i] = np.interp(pos_new, pos_old, result.x_profile[:, i])
            y_new[:, i] = np.interp(pos_new, pos_old, result.y_profile[:, i])

        # Normalize compositions
        for j in range(N_new):
            x_sum = x_new[j].sum()
            if x_sum > 0:
                x_new[j] /= x_sum
            y_sum = y_new[j].sum()
            if y_sum > 0:
                y_new[j] /= y_sum

        # Pack into flat x0 vector: [T, x(6), y(6)] per stage = 13 per stage
        x0 = np.zeros(N_new * (1 + Nc + Nc))
        for j in range(N_new):
            offset = j * (1 + Nc + Nc)
            x0[offset] = T_new[j]
            x0[offset + 1: offset + 1 + Nc] = x_new[j]
            x0[offset + 1 + Nc: offset + 1 + 2 * Nc] = y_new[j]

        return x0

    def _result_to_x0(self, result: ColumnResult) -> np.ndarray:
        """Convert a ColumnResult back to a flat x0 vector."""
        N = len(result.T_profile)
        Nc = result.x_profile.shape[1]
        x0 = np.zeros(N * (1 + Nc + Nc))
        for j in range(N):
            offset = j * (1 + Nc + Nc)
            x0[offset] = result.T_profile[j]
            x0[offset + 1: offset + 1 + Nc] = result.x_profile[j]
            x0[offset + 1 + Nc: offset + 1 + 2 * Nc] = result.y_profile[j]
        return x0
