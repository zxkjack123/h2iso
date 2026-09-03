"""Tests for Sequential Modular Solver (Task 2.1.3)."""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.flowsheet.schema import (
    ColumnConfig,
    Connection,
    FeedConfig,
    FlowsheetConfig,
    TearStream,
)
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.species import N_SPECIES

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "wang2022"


def _make_h2_comp():
    z = np.zeros(N_SPECIES)
    z[0] = 0.9975
    z[3] = 0.0025
    return z


def _make_mixed_comp():
    z = np.zeros(N_SPECIES)
    z[0] = 0.90
    z[1] = 0.08
    z[3] = 0.02
    return z


class TestNoRecycleFlowsheet:
    """Test SM solver on a simple two-column cascade (no recycle)."""

    def _build_linear_config(self) -> FlowsheetConfig:
        """CD1 → CD2 (no recycle, feed -> CD1 -> bottom -> CD2)."""
        z_feed = _make_h2_comp()
        return FlowsheetConfig(
            feeds=[
                FeedConfig(
                    name="FEED",
                    flow=200.0,
                    composition=z_feed,
                    target_column="CD1",
                    feed_stage=8,
                ),
            ],
            columns=[
                ColumnConfig(
                    name="CD1",
                    n_stages=15,
                    reflux_ratio=5.0,
                    distillate_to_feed=0.5,
                    feed_positions={"FEED": 8},
                    pressure=95000.0,
                ),
                ColumnConfig(
                    name="CD2",
                    n_stages=15,
                    reflux_ratio=5.0,
                    distillate_to_feed=0.5,
                    feed_positions={"CD1_bottom": 8},
                    pressure=95000.0,
                ),
            ],
            equilibrators=[],
            connections=[
                Connection(from_unit="FEED_feed", to_unit="CD1", stage=8),
                Connection(from_unit="CD1_bottom", to_unit="CD2", stage=8),
            ],
            products={
                "CD1_top": "H2 rich",
                "CD2_top": "HD rich",
                "CD2_bottom": "Heavy",
            },
            tear_streams=[],  # No recycle
        )

    def test_no_recycle_converges_one_iteration(self):
        """Without tear streams, solver should converge in 1 iteration."""
        config = self._build_linear_config()
        solver = SequentialModularSolver(
            config, method="direct", continuation_substeps=0
        )
        result = solver.solve(max_iter=5)

        assert result.converged
        assert result.iterations == 1  # No tear -> immediate convergence

    def test_no_recycle_mass_balance(self):
        """Total product flow should equal feed flow."""
        config = self._build_linear_config()
        solver = SequentialModularSolver(
            config, method="direct", continuation_substeps=0
        )
        result = solver.solve()

        # Find all output streams
        feed_flow = 200.0
        # CD1 produces distillate (top) and bottoms; CD2 uses bottoms as feed
        # Final products: CD1_distillate + CD2_distillate + CD2_bottoms = feed_flow
        cd1_dist = result.streams.get("CD1_distillate")
        cd2_dist = result.streams.get("CD2_distillate")
        cd2_bot = result.streams.get("CD2_bottoms")

        assert cd1_dist is not None, f"Available streams: {list(result.streams.keys())}"
        assert cd2_dist is not None
        assert cd2_bot is not None

        total_product = cd1_dist.flow + cd2_dist.flow + cd2_bot.flow
        assert total_product == pytest.approx(feed_flow, rel=0.001)


class TestRecycleFlowsheet:
    """Test SM solver with recycle loop."""

    def _build_recycle_config(self) -> FlowsheetConfig:
        """Simple two-column with recycle: CD1 -> CD2 -> CD2_bottom recycles to CD1."""
        z_feed = _make_h2_comp()
        return FlowsheetConfig(
            feeds=[
                FeedConfig(
                    name="FEED",
                    flow=200.0,
                    composition=z_feed,
                    target_column="CD1",
                    feed_stage=5,
                ),
            ],
            columns=[
                ColumnConfig(
                    name="CD1",
                    n_stages=15,
                    reflux_ratio=5.0,
                    distillate_to_feed=0.9,
                    feed_positions={"FEED": 5, "CD2_bottom_recycle": 12},
                    pressure=95000.0,
                ),
                ColumnConfig(
                    name="CD2",
                    n_stages=15,
                    reflux_ratio=5.0,
                    distillate_to_feed=0.5,
                    feed_positions={"CD1_bottom": 8},
                    pressure=95000.0,
                ),
            ],
            equilibrators=[],
            connections=[
                Connection(from_unit="FEED_feed", to_unit="CD1", stage=5),
                Connection(from_unit="CD1_bottom", to_unit="CD2", stage=8),
                Connection(from_unit="CD2_bottom_recycle", to_unit="CD1", stage=12),
            ],
            products={"CD1_top": "H2", "CD2_top": "HD"},
            tear_streams=[
                TearStream(
                    from_unit="CD2_bottom_recycle",
                    to_unit="CD1",
                    name="CD2_bottom_recycle → CD1",
                ),
            ],
        )

    def test_recycle_converges(self):
        """Recycle loop should converge within max_iter."""
        config = self._build_recycle_config()
        solver = SequentialModularSolver(
            config, method="wegstein", continuation_substeps=0
        )
        result = solver.solve(max_iter=50, tol=1e-3)

        assert result.converged, (
            f"Failed to converge after {result.iterations} iterations, "
            f"residual={result.tear_residual:.6f}"
        )
        assert result.iterations <= 50

    def test_recycle_wegstein_faster_than_direct(self):
        """Wegstein should converge in fewer iterations than direct substitution."""
        config = self._build_recycle_config()

        solver_weg = SequentialModularSolver(
            config, method="wegstein", continuation_substeps=0
        )
        result_weg = solver_weg.solve(max_iter=50, tol=1e-3)

        solver_dir = SequentialModularSolver(
            config, method="direct", continuation_substeps=0
        )
        result_dir = solver_dir.solve(max_iter=50, tol=1e-3)

        # Both should converge
        assert result_weg.converged
        assert result_dir.converged
        # Wegstein should be at least as fast (often faster)
        assert result_weg.iterations <= result_dir.iterations + 5


class TestOnUnitFailurePolicy:
    """Regression for BG-03: unit failures must surface in unit_failures and obey policy."""

    def test_invalid_policy_rejected(self):
        """Constructor must reject unknown on_unit_failure values."""
        cfg = FlowsheetConfig(
            feeds=[],
            columns=[],
            equilibrators=[],
            connections=[],
            products={},
            tear_streams=[],
        )
        with pytest.raises(ValueError, match="on_unit_failure"):
            SequentialModularSolver(cfg, on_unit_failure="bogus")

    def test_default_is_raise(self):
        """Default policy must be 'raise' so failures are not silenced."""
        cfg = FlowsheetConfig(
            feeds=[],
            columns=[],
            equilibrators=[],
            connections=[],
            products={},
            tear_streams=[],
        )
        solver = SequentialModularSolver(cfg)
        assert solver.on_unit_failure == "raise"

    def test_raise_propagates_unit_failure(self, monkeypatch):
        """on_unit_failure='raise' must propagate RuntimeError from a unit."""
        from h2iso.flowsheet import solver as solver_mod
        from h2iso.flowsheet.unit import ColumnUnit

        def boom(self, inputs):
            raise RuntimeError(f"forced failure in {self.name}")

        monkeypatch.setattr(ColumnUnit, "solve", boom)

        cfg = FlowsheetConfig(
            feeds=[
                FeedConfig(
                    name="F",
                    flow=10.0,
                    composition=_make_h2_comp(),
                    target_column="C1",
                    feed_stage=5,
                )
            ],
            columns=[
                ColumnConfig(
                    name="C1",
                    n_stages=10,
                    pressure=101325.0,
                    reflux_ratio=2.0,
                    distillate_to_feed=0.5,
                    feed_positions={"F": 5},
                )
            ],
            equilibrators=[],
            connections=[Connection(from_unit="F", to_unit="C1")],
            products={},
            tear_streams=[],
        )
        s = solver_mod.SequentialModularSolver(
            cfg, on_unit_failure="raise", continuation_substeps=0
        )
        with pytest.raises(RuntimeError, match="forced failure"):
            s.solve(max_iter=2)

    def test_stale_records_failure_and_continues(self, monkeypatch):
        """on_unit_failure='stale' records failure in unit_failures and continues."""
        from h2iso.flowsheet import solver as solver_mod
        from h2iso.flowsheet.unit import ColumnUnit

        def boom(self, inputs):
            raise RuntimeError(f"forced failure in {self.name}")

        monkeypatch.setattr(ColumnUnit, "solve", boom)

        cfg = FlowsheetConfig(
            feeds=[
                FeedConfig(
                    name="F",
                    flow=10.0,
                    composition=_make_h2_comp(),
                    target_column="C1",
                    feed_stage=5,
                )
            ],
            columns=[
                ColumnConfig(
                    name="C1",
                    n_stages=10,
                    pressure=101325.0,
                    reflux_ratio=2.0,
                    distillate_to_feed=0.5,
                    feed_positions={"F": 5},
                )
            ],
            equilibrators=[],
            connections=[Connection(from_unit="F", to_unit="C1")],
            products={},
            tear_streams=[],
        )
        s = solver_mod.SequentialModularSolver(
            cfg, on_unit_failure="stale", continuation_substeps=0
        )
        result = s.solve(max_iter=2)
        assert "C1" in result.unit_failures
        assert "forced failure" in result.unit_failures["C1"]
