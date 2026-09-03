"""Tests for ContinuationSolver multi-feed adaptation (Task 2.0.2)."""

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.mesh.column import ColumnSpec, FeedSpec
from h2iso.mesh.continuation import ContinuationSolver


@pytest.fixture
def h2_dominant():
    """H2-dominant composition."""
    z = np.zeros(6)
    z[0] = 0.9975  # H2
    z[3] = 0.0025  # D2
    return z


@pytest.fixture
def mixed_hd():
    """Mixed H2/HD composition."""
    z = np.zeros(6)
    z[0] = 0.90  # H2
    z[1] = 0.08  # HD
    z[3] = 0.02  # D2
    return z


class TestScaleFeeds:
    """Test _scale_feeds() helper."""

    def test_none_feeds_returns_none(self, h2_dominant):
        spec = ColumnSpec(
            n_stages=20,
            feed_stage=10,
            feed_flow=100.0,
            feed_composition=h2_dominant,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=None,
        )
        result = ContinuationSolver._scale_feeds(spec, 40)
        assert result is None

    def test_proportional_scaling(self, h2_dominant, mixed_hd):
        feeds = [
            FeedSpec(stage=5, flow=60.0, composition=h2_dominant),
            FeedSpec(stage=10, flow=30.0, composition=mixed_hd),
            FeedSpec(stage=15, flow=10.0, composition=h2_dominant),
        ]
        spec = ColumnSpec(
            n_stages=20,
            feed_stage=5,
            feed_flow=100.0,
            feed_composition=h2_dominant,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )

        # Scale to 40 stages (2x)
        scaled = ContinuationSolver._scale_feeds(spec, 40)
        assert scaled is not None
        assert len(scaled) == 3
        # Proportional: 5/20*40=10, 10/20*40=20, 15/20*40=30
        assert scaled[0].stage == 10
        assert scaled[1].stage == 20
        assert scaled[2].stage == 30
        # Flows preserved
        assert scaled[0].flow == 60.0
        assert scaled[1].flow == 30.0
        assert scaled[2].flow == 10.0

    def test_boundary_clamping(self, h2_dominant):
        """Feed at stage 1 should be clamped to at least stage 2."""
        feeds = [FeedSpec(stage=1, flow=100.0, composition=h2_dominant)]
        spec = ColumnSpec(
            n_stages=20,
            feed_stage=1,
            feed_flow=100.0,
            feed_composition=h2_dominant,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )
        scaled = ContinuationSolver._scale_feeds(spec, 10)
        # 1/20*10 = 0.5 rounds to 1 -> clamped to 2
        assert scaled[0].stage >= 2


class TestMultiFeedContinuation:
    """Test continuation with multi-feed columns."""

    def test_three_feed_continuation_15_to_30(self, h2_dominant, mixed_hd):
        """Three-feed column continuation from 15 to 30 stages."""
        feeds = [
            FeedSpec(stage=4, flow=50.0, composition=h2_dominant),
            FeedSpec(stage=8, flow=30.0, composition=mixed_hd),
            FeedSpec(stage=12, flow=20.0, composition=h2_dominant),
        ]
        base_spec = ColumnSpec(
            n_stages=15,
            feed_stage=4,
            feed_flow=100.0,
            feed_composition=h2_dominant,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )

        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=2)
        result = solver.solve(base_spec)

        assert result.final.convergence_info["success"]
        assert len(result.final.T_profile) == 30

    def test_three_feed_continuation_15_to_60(self, h2_dominant, mixed_hd):
        """Three-feed column continuation from 15 to 60 stages (ISS-O scale)."""
        feeds = [
            FeedSpec(stage=4, flow=50.0, composition=h2_dominant),
            FeedSpec(stage=8, flow=30.0, composition=mixed_hd),
            FeedSpec(stage=12, flow=20.0, composition=h2_dominant),
        ]
        base_spec = ColumnSpec(
            n_stages=15,
            feed_stage=4,
            feed_flow=100.0,
            feed_composition=h2_dominant,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )

        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=2)
        solver.add_step("N", target=60, n_substeps=3)
        result = solver.solve(base_spec)

        assert result.final.convergence_info["success"]
        assert len(result.final.T_profile) == 60
        # T profile monotonically non-decreasing
        assert np.all(np.diff(result.final.T_profile) >= -0.1)

    def test_feeds_preserved_through_R_continuation(self, h2_dominant, mixed_hd):
        """Multi-feed should be preserved through reflux ratio continuation."""
        feeds = [
            FeedSpec(stage=5, flow=60.0, composition=h2_dominant),
            FeedSpec(stage=12, flow=40.0, composition=mixed_hd),
        ]
        base_spec = ColumnSpec(
            n_stages=15,
            feed_stage=5,
            feed_flow=100.0,
            feed_composition=h2_dominant,
            pressure=101325.0,
            reflux_ratio=3.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )

        solver = ContinuationSolver()
        solver.add_step("R", target=6.0, n_substeps=3)
        result = solver.solve(base_spec)

        assert result.final.convergence_info["success"]
