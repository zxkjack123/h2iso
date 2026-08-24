"""Sequential Modular (SM) flowsheet solver with Wegstein acceleration."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from h2iso.flowsheet.schema import FlowsheetConfig, TearStream
from h2iso.flowsheet.stream import Stream
from h2iso.flowsheet.unit import (
    ColumnUnit,
    EquilibratorUnit,
    UnitOp,
)
from h2iso.mesh.column import ColumnResult
from h2iso.species import N_SPECIES


@dataclass
class FlowsheetResult:
    """Result from flowsheet solve."""

    streams: dict[str, Stream]
    column_results: dict[str, ColumnResult] = field(default_factory=dict)
    converged: bool = False
    iterations: int = 0
    tear_residual: float = float("inf")
    unit_failures: dict[str, str] = field(default_factory=dict)


class SequentialModularSolver:
    """Sequential modular flowsheet solver with Wegstein acceleration.

    Solves multi-unit flowsheets by iterating over units in topological
    order, with tear streams to break recycle loops.

    Parameters
    ----------
    config : FlowsheetConfig
        Flowsheet configuration.
    method : str
        Convergence acceleration method: "direct" or "wegstein".
    continuation_substeps : int
        Substeps for column continuation solver. 0 = direct solve.
    on_unit_failure : Literal["raise", "skip", "stale"]
        Policy when a UnitOp.solve() raises RuntimeError during
        flowsheet iteration (BG-03). "raise" (default) propagates the
        error immediately. "stale" keeps previous-iteration stream
        values and continues (original silent behaviour, but the failure
        is now recorded in FlowsheetResult.unit_failures). "skip" is a
        synonym of "stale" for the sequential modular driver.
    """

    def __init__(
        self,
        config: FlowsheetConfig,
        method: str = "wegstein",
        continuation_substeps: int = 3,
        on_unit_failure: Literal["raise", "skip", "stale"] = "raise",
    ):
        self.config = config
        if method not in ("direct", "wegstein"):
            raise ValueError(
                f"method must be 'direct' or 'wegstein' (case-sensitive); got {method!r}"
            )
        self.method = method
        self.continuation_substeps = continuation_substeps
        if on_unit_failure not in ("raise", "skip", "stale"):
            raise ValueError(
                f"on_unit_failure must be one of 'raise', 'skip', 'stale'; "
                f"got {on_unit_failure!r}"
            )
        self.on_unit_failure = on_unit_failure
        self.units: dict[str, UnitOp] = {}
        self.streams: dict[str, Stream] = {}
        self._unit_failures: dict[str, str] = {}
        self._build_units()

    def _build_units(self):
        """Instantiate UnitOp objects from config."""
        for col_cfg in self.config.columns:
            # Determine feed stages from feed_positions
            feed_stages = list(col_cfg.feed_positions.values())
            self.units[col_cfg.name] = ColumnUnit(
                name=col_cfg.name,
                n_stages=col_cfg.n_stages,
                pressure=col_cfg.pressure,
                reflux_ratio=col_cfg.reflux_ratio,
                distillate_to_feed=col_cfg.distillate_to_feed,
                feed_stages=feed_stages if feed_stages else None,
                continuation_substeps=self.continuation_substeps,
                eos=col_cfg.eos,
            )

        for eq_cfg in self.config.equilibrators:
            self.units[eq_cfg.name] = EquilibratorUnit(
                name=eq_cfg.name,
                temperature=eq_cfg.temperature,
            )

    def solve(self, max_iter: int = 50, tol: float = 1e-4) -> FlowsheetResult:
        """Solve the flowsheet iteratively.

        Parameters
        ----------
        max_iter : int
            Maximum iterations for tear stream convergence.
        tol : float
            Convergence tolerance on tear stream composition.

        Returns
        -------
        FlowsheetResult
        """
        # Determine calculation order and tear points
        calc_order = self._build_calculation_order()
        tear_streams = self.config.tear_streams

        # Initialize tear stream estimates
        tear_values = self._initialize_tears(tear_streams)

        # Previous values for Wegstein
        tear_prev: dict[str, np.ndarray] | None = None
        tear_g_prev: dict[str, np.ndarray] | None = None

        converged = False
        iteration = 0
        residual = float("inf")

        for iteration in range(1, max_iter + 1):
            # Set tear stream values into stream bank
            for tear in tear_streams:
                self.streams[tear.name] = tear_values[tear.name]

            # Execute units in calculation order
            self._execute_sequence(calc_order)

            # Check tear stream convergence
            if not tear_streams:
                converged = True
                break

            # Compute new tear values from unit outputs
            tear_new = {}
            residual = 0.0
            for tear in tear_streams:
                new_stream = self._get_tear_output(tear)
                if new_stream is not None:
                    tear_new[tear.name] = new_stream
                    old = tear_values[tear.name]
                    diff = np.abs(new_stream.composition - old.composition).max()
                    flow_diff = abs(new_stream.flow - old.flow) / max(old.flow, 1e-10)
                    residual = max(residual, diff, flow_diff)

            if residual < tol:
                converged = True
                break

            # Update tear estimates
            if (
                self.method == "wegstein"
                and tear_prev is not None
                and tear_g_prev is not None
            ):
                # Save current state before update
                x_prev_new = {
                    k: np.concatenate([[v.flow], v.composition])
                    for k, v in tear_values.items()
                }
                g_prev_new = {
                    k: np.concatenate([[v.flow], v.composition])
                    for k, v in tear_new.items()
                }
                tear_values = self._wegstein_update(
                    tear_values, tear_new, tear_prev, tear_g_prev
                )
                tear_prev = x_prev_new
                tear_g_prev = g_prev_new
            else:
                # Direct substitution for first iteration or direct method
                tear_prev = {
                    k: np.concatenate([[v.flow], v.composition])
                    for k, v in tear_values.items()
                }
                tear_g_prev = {
                    k: np.concatenate([[v.flow], v.composition])
                    for k, v in tear_new.items()
                }
                tear_values = tear_new

        # Collect column results
        column_results = {}
        for name, unit in self.units.items():
            if isinstance(unit, ColumnUnit) and hasattr(unit, "_last_result"):
                column_results[name] = unit._last_result

        return FlowsheetResult(
            streams=dict(self.streams),
            column_results=column_results,
            converged=converged,
            iterations=iteration,
            tear_residual=residual,
            unit_failures=dict(self._unit_failures),
        )

    def _build_calculation_order(self) -> list[str]:
        """Build topological execution order for units.

        Returns unit names in order that respects dependency flow,
        with tear streams broken.
        """
        # Build dependency graph without tear stream edges
        tear_edges = {(t.from_unit, t.to_unit) for t in self.config.tear_streams}

        # Nodes = all units
        nodes = set(self.units.keys())
        # Build edges from connections
        in_degree: dict[str, int] = {n: 0 for n in nodes}
        adj: dict[str, list[str]] = {n: [] for n in nodes}

        for conn in self.config.connections:
            from_node = self._conn_to_unit(conn.from_unit)
            to_node = self._conn_to_unit(conn.to_unit)

            if from_node is None or to_node is None:
                continue
            if from_node == to_node:
                continue
            # Skip tear stream edges
            if (conn.from_unit, conn.to_unit) in tear_edges:
                continue

            if to_node in nodes and from_node in nodes:
                adj[from_node].append(to_node)
                in_degree[to_node] += 1

        # Topological sort (Kahn's algorithm)
        queue = [n for n in nodes if in_degree[n] == 0]
        order = []
        while queue:
            # Pick node with lowest in-degree (deterministic)
            queue.sort()
            node = queue.pop(0)
            order.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Add any remaining nodes not in order (isolated units)
        for n in nodes:
            if n not in order:
                order.append(n)

        return order

    def _conn_to_unit(self, name: str) -> str | None:
        """Map a connection endpoint name to a unit name."""
        # Direct match
        if name in self.units:
            return name
        # Column output: CD1_bottom -> CD1, CD3_top -> CD3
        for unit_name in self.units:
            if name.startswith(unit_name + "_"):
                return unit_name
        # External feed (not a unit)
        return None

    def _initialize_tears(self, tear_streams: list[TearStream]) -> dict[str, Stream]:
        """Initialize tear stream estimates from external feeds."""
        tears = {}
        for tear in tear_streams:
            # Use a small flow with averaged feed composition as initial guess
            if self.config.feeds:
                avg_z = np.zeros(N_SPECIES)
                total_f = 0.0
                for f in self.config.feeds:
                    avg_z += f.flow * f.composition
                    total_f += f.flow
                avg_z /= total_f
                # Initial tear: 10% of total feed flow
                init_flow = total_f * 0.1
            else:
                avg_z = np.ones(N_SPECIES) / N_SPECIES
                init_flow = 10.0

            tears[tear.name] = Stream(
                flow=init_flow,
                composition=avg_z,
                temperature=22.0,
                pressure=101325.0,
            )
        return tears

    def _execute_sequence(self, calc_order: list[str]):
        """Execute all units in order, collecting and routing streams."""
        for unit_name in calc_order:
            unit = self.units[unit_name]
            inputs = self._collect_inputs(unit_name)
            if not inputs:
                continue

            try:
                outputs = unit.solve(inputs)
                # Store outputs in stream bank
                for out_key, out_stream in outputs.items():
                    stream_id = f"{unit_name}_{out_key}"
                    self.streams[stream_id] = out_stream
                # ColumnUnit persists its ColumnResult on self._last_result
                # inside solve() (BG-01); we collect it after the loop.
                # Clear any prior failure entry on success.
                self._unit_failures.pop(unit_name, None)
            except RuntimeError as exc:
                # BG-03: record the failure and dispatch by policy.
                self._unit_failures[unit_name] = str(exc)
                if self.on_unit_failure == "raise":
                    raise
                # "skip" and "stale" both keep previous values for this
                # iteration; in the sequential modular driver the outer
                # iteration revisits the unit, so the two are equivalent
                # here. "stale" preserves the original silent behaviour
                # but the failure is now visible in unit_failures.
                continue

    def _collect_inputs(self, unit_name: str) -> dict[str, Stream]:
        """Collect input streams for a unit from connections and external feeds."""
        inputs: dict[str, Stream] = {}

        # Get column config to know feed_positions ordering
        col_cfg = next((c for c in self.config.columns if c.name == unit_name), None)

        if col_cfg is not None:
            # For columns, map feed names to their streams
            for feed_name, stage in col_cfg.feed_positions.items():
                stream = self._resolve_stream(feed_name, unit_name)
                if stream is not None:
                    inputs[feed_name] = stream
        else:
            # For other units, collect all incoming connections
            for conn in self.config.connections:
                to_unit = self._conn_to_unit(conn.to_unit)
                if to_unit == unit_name:
                    stream = self._resolve_stream(conn.from_unit, unit_name)
                    if stream is not None:
                        # Apply splitter ratio if configured
                        stream = self._apply_split(stream, conn.from_unit, unit_name)
                        inputs[conn.from_unit] = stream

        return inputs

    def _apply_split(
        self,
        stream: Stream,
        source_name: str,
        target_unit: str,
    ) -> Stream:
        """Scale a stream by splitter ratio if a splitter is configured.

        Returns a new Stream with flow *= ratio. If no splitter matches,
        returns the original stream unchanged.
        """
        split_config = self.config.splitter.get(source_name)
        if split_config is None:
            return stream
        ratio = split_config.get(target_unit)
        if ratio is None:
            return stream
        result = copy.copy(stream)
        result.flow *= ratio
        return result

    def _resolve_stream(self, source_name: str, target_unit: str) -> Stream | None:
        """Resolve a stream source name to an actual Stream object."""
        # Check if it's a tear stream
        for tear in self.config.tear_streams:
            # Match tear by source name
            if source_name == tear.from_unit:
                return self.streams.get(tear.name)

        # Check if it matches an external feed
        for feed in self.config.feeds:
            if source_name == feed.name or source_name == feed.name + "_feed":
                return Stream(
                    flow=feed.flow,
                    composition=feed.composition.copy(),
                    temperature=22.0,
                    pressure=101325.0,
                )

        # Check stream bank for unit outputs
        # e.g., "CD1_bottom" -> look for stream "CD1_bottoms" or "CD1_bottom"
        # Try exact match
        if source_name in self.streams:
            return self.streams[source_name]

        # Try unit output patterns
        for key, stream in self.streams.items():
            if key == source_name:
                return stream
            # CD1_bottom matches CD1_bottoms
            if source_name + "s" == key or key + "s" == source_name:
                return stream
            # CD3_top matches CD3_distillate
            if source_name.endswith("_top"):
                base = source_name.rsplit("_top", 1)[0]
                if key == f"{base}_distillate":
                    return stream
            if source_name.endswith("_bottom"):
                base = source_name.rsplit("_bottom", 1)[0]
                if key == f"{base}_bottoms":
                    return stream

        # Check equilibrator output: match by name precisely.
        # EquilibratorUnit outputs are stored as "{name}_out".
        for eq_cfg in self.config.equilibrators:
            eq_name = eq_cfg.name
            expected_key = f"{eq_name}_out"
            if source_name == eq_name and expected_key in self.streams:
                return self.streams[expected_key]
            # Also try if source_name matches equilibrator name with suffix variants
            if source_name == eq_name + "_output" and expected_key in self.streams:
                return self.streams[expected_key]
            if source_name == eq_name:
                for key, stream in self.streams.items():
                    if key == expected_key:
                        return stream

        # Backward compat: ISS-O has a single equilibrator named "equilibrator"
        # whose output is "equilibrator_out"
        if (
            source_name in ("equilibrator", "equilibrator_output")
            and "equilibrator_out" in self.streams
        ):
            return self.streams["equilibrator_out"]

        return None

    def _get_tear_output(self, tear: TearStream) -> Stream | None:
        """Get the computed output for a tear stream after unit execution."""
        # The tear's from_unit produced an output; find it
        from_unit = self._conn_to_unit(tear.from_unit)
        if from_unit is None:
            return None

        # Look for the specific output
        # e.g., tear from "CD2_bottom_recycle" -> unit is CD2, output is "bottoms"
        suffix = (
            tear.from_unit.replace(from_unit + "_", "")
            if from_unit in tear.from_unit
            else ""
        )

        # Map common suffixes to unit output keys
        if "bottom" in suffix:
            key = f"{from_unit}_bottoms"
        elif "top" in suffix:
            key = f"{from_unit}_distillate"
        else:
            key = f"{from_unit}_out"

        return self.streams.get(key)

    def _wegstein_update(
        self,
        x_curr: dict[str, Stream],
        g_curr: dict[str, Stream],
        x_prev: dict[str, np.ndarray],
        g_prev: dict[str, np.ndarray] | None,
    ) -> dict[str, Stream]:
        """Wegstein acceleration for tear stream convergence.

        q = (s) / (s - 1) where s = (g_k - g_{k-1}) / (x_k - x_{k-1})
        x_{k+1} = (1-q)*g_k + q*x_k

        Bounded: q in [-5, 0.9] to ensure stability.
        """
        updated = {}
        new_x_prev = {}
        new_g_prev = {}

        for name in x_curr:
            x_vec = np.concatenate([[x_curr[name].flow], x_curr[name].composition])
            g_vec = np.concatenate([[g_curr[name].flow], g_curr[name].composition])

            if name in x_prev and g_prev is not None and name in g_prev:
                xp = x_prev[name]
                gp = g_prev[name]
                dx = x_vec - xp
                dg = g_vec - gp

                # Element-wise Wegstein parameter
                with np.errstate(divide="ignore", invalid="ignore"):
                    s = np.where(np.abs(dx) > 1e-12, dg / dx, np.zeros_like(dx))
                q = np.clip(s / (s - 1), -5.0, 0.9)

                x_new = (1 - q) * g_vec + q * x_vec
                # Ensure non-negative
                x_new = np.clip(x_new, 0.0, None)
            else:
                # Direct substitution
                x_new = g_vec

            new_x_prev[name] = x_vec
            new_g_prev[name] = g_vec

            # Reconstruct stream — preserve composition simplex:
            #   x_new[0] is flow (scalar); x_new[1:] is the composition vector.
            # The Wegstein/direct update may break sum-to-one and produce small
            # negatives. Clip negatives then radially renormalise (symmetric
            # simplex projection); this avoids biasing any single component the
            # way an asymmetric (tail = 1 - sum(head)) closure would.
            flow_new = max(x_new[0], 0.1)
            comp_raw = np.clip(x_new[1:], 0.0, None)
            comp_sum = comp_raw.sum()
            if comp_sum > 0:
                comp_new = comp_raw / comp_sum
            else:
                comp_new = np.ones(N_SPECIES) / N_SPECIES

            updated[name] = Stream(
                flow=flow_new,
                composition=comp_new,
                temperature=x_curr[name].temperature,
                pressure=x_curr[name].pressure,
            )

        # Store for next iteration (update class state via closure pattern)
        # We need a better way — use a simple update of the external dicts
        # Actually we rebuild x_prev/g_prev each iteration via the solve loop
        # So just return the updated values and handle state in solve()
        self._last_x_prev = new_x_prev
        self._last_g_prev = new_g_prev

        return updated
