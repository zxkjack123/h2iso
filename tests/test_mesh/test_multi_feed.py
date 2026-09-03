"""Tests for multi-feed column support (Task 2.0.1)."""

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.mesh.column import Column, ColumnSpec, FeedSpec
from h2iso.species import N_SPECIES


@pytest.fixture
def h2_dominant_composition():
    """H2-dominant feed composition (Wang 2022 WDS-like)."""
    z = np.zeros(N_SPECIES)
    z[0] = 0.9975  # H2
    z[3] = 0.0025  # D2
    return z


@pytest.fixture
def mixed_hd_composition():
    """Mixed H2/HD composition."""
    z = np.zeros(N_SPECIES)
    z[0] = 0.90  # H2
    z[1] = 0.08  # HD
    z[3] = 0.02  # D2
    return z


class TestFeedSpec:
    """Test FeedSpec dataclass."""

    def test_creation(self, h2_dominant_composition):
        f = FeedSpec(stage=10, flow=100.0, composition=h2_dominant_composition)
        assert f.stage == 10
        assert f.flow == 100.0
        assert f.quality == 1.0  # default
        np.testing.assert_array_equal(f.composition, h2_dominant_composition)

    def test_custom_quality(self, h2_dominant_composition):
        f = FeedSpec(stage=5, flow=50.0, composition=h2_dominant_composition, quality=0.5)
        assert f.quality == 0.5


class TestMultiFeedComputeFlows:
    """Test _compute_flows() with multiple feeds."""

    def test_single_feed_via_feeds_list_matches_legacy(self, h2_dominant_composition):
        """Single feed via feeds=[FeedSpec(...)] should match legacy single-feed."""
        spec_legacy = ColumnSpec(
            n_stages=20,
            feed_stage=10,
            feed_flow=100.0,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feed_quality=1.0,
        )
        spec_multi = ColumnSpec(
            n_stages=20,
            feed_stage=10,
            feed_flow=100.0,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=[FeedSpec(stage=10, flow=100.0, composition=h2_dominant_composition, quality=1.0)],
        )
        col_legacy = Column(spec_legacy)
        col_multi = Column(spec_multi)

        L_leg, V_leg = col_legacy._compute_flows()
        L_multi, V_multi = col_multi._compute_flows()

        np.testing.assert_allclose(L_leg, L_multi)
        np.testing.assert_allclose(V_leg, V_multi)

    def test_two_feeds_creates_three_sections(self, h2_dominant_composition):
        """Two feeds should create 3 L/V sections (rectifying, middle, stripping)."""
        feeds = [
            FeedSpec(stage=7, flow=60.0, composition=h2_dominant_composition, quality=1.0),
            FeedSpec(stage=14, flow=40.0, composition=h2_dominant_composition, quality=1.0),
        ]
        spec = ColumnSpec(
            n_stages=20,
            feed_stage=7,  # legacy (unused when feeds is set)
            feed_flow=100.0,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )
        col = Column(spec)
        L, V = col._compute_flows()

        # Check we have 3 distinct L sections (ignoring V[0]=0 and L[-1]=B)
        # Section 1: stages 1-6 (indices 0-5, above feed 1)
        # Section 2: stages 7-13 (indices 6-12, between feeds)
        # Section 3: stages 14-20 (indices 13-19, below feed 2)
        F_total = 100.0
        D = 0.5 * F_total
        R = 5.0

        # Rectifying (above all feeds): L = R*D = 250
        assert L[1] == pytest.approx(R * D)
        assert L[5] == pytest.approx(R * D)

        # Middle section (below feed 1, above feed 2): L = R*D + q1*F1 = 250 + 60 = 310
        assert L[6] == pytest.approx(R * D + 60.0)
        assert L[12] == pytest.approx(R * D + 60.0)

        # Stripping (below feed 2): L = R*D + q1*F1 + q2*F2 = 250 + 60 + 40 = 350
        assert L[13] == pytest.approx(R * D + 60.0 + 40.0)
        assert L[18] == pytest.approx(R * D + 60.0 + 40.0)

        # V should be constant above all feeds (except V[0]=0)
        assert V[1] == pytest.approx((R + 1) * D)  # 300
        assert V[5] == pytest.approx((R + 1) * D)

        # V in middle section stays same for q=1 feeds: (R+1)*D - (1-1)*F1 = 300
        assert V[6] == pytest.approx((R + 1) * D)
        assert V[12] == pytest.approx((R + 1) * D)

        # V in stripping stays same for q=1 feeds
        assert V[13] == pytest.approx((R + 1) * D)

    def test_symmetric_double_feed_equals_single_double_flow(self, h2_dominant_composition):
        """Two equal feeds at same stage should give same L/V as single feed at 2x flow."""
        stage = 10
        flow = 50.0
        feeds_double = [
            FeedSpec(stage=stage, flow=flow, composition=h2_dominant_composition),
            FeedSpec(stage=stage, flow=flow, composition=h2_dominant_composition),
        ]
        spec_double = ColumnSpec(
            n_stages=20,
            feed_stage=stage,
            feed_flow=2 * flow,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds_double,
        )
        spec_single = ColumnSpec(
            n_stages=20,
            feed_stage=stage,
            feed_flow=2 * flow,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
        )
        col_double = Column(spec_double)
        col_single = Column(spec_single)

        L_d, V_d = col_double._compute_flows()
        L_s, V_s = col_single._compute_flows()

        np.testing.assert_allclose(L_d, L_s)
        np.testing.assert_allclose(V_d, V_s)


class TestMultiFeedSolve:
    """Test column NLP solve with multiple feeds."""

    def test_dual_feed_converges(self, h2_dominant_composition, mixed_hd_composition):
        """A dual-feed column should converge."""
        feeds = [
            FeedSpec(stage=8, flow=80.0, composition=h2_dominant_composition, quality=1.0),
            FeedSpec(stage=15, flow=40.0, composition=mixed_hd_composition, quality=1.0),
        ]
        spec = ColumnSpec(
            n_stages=20,
            feed_stage=8,
            feed_flow=120.0,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )
        col = Column(spec)
        result = col.solve()

        assert result.convergence_info["success"], (
            f"Dual-feed column failed: {result.convergence_info['status']}"
        )
        # Temperature profile should be monotonically non-decreasing
        assert np.all(np.diff(result.T_profile) >= -0.1)
        # Compositions should sum to 1
        np.testing.assert_allclose(result.x_profile.sum(axis=1), 1.0, atol=1e-6)
        np.testing.assert_allclose(result.y_profile.sum(axis=1), 1.0, atol=1e-6)

    def test_symmetric_feeds_same_stage_matches_single(self, h2_dominant_composition):
        """Two equal feeds at same stage should produce same result as single 2x feed."""
        stage = 10
        flow = 50.0
        feeds = [
            FeedSpec(stage=stage, flow=flow, composition=h2_dominant_composition),
            FeedSpec(stage=stage, flow=flow, composition=h2_dominant_composition),
        ]
        spec_multi = ColumnSpec(
            n_stages=20,
            feed_stage=stage,
            feed_flow=2 * flow,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feeds=feeds,
        )
        spec_single = ColumnSpec(
            n_stages=20,
            feed_stage=stage,
            feed_flow=2 * flow,
            feed_composition=h2_dominant_composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
        )
        result_multi = Column(spec_multi).solve()
        result_single = Column(spec_single).solve()

        assert result_multi.convergence_info["success"]
        assert result_single.convergence_info["success"]

        # Profiles should be essentially identical
        np.testing.assert_allclose(
            result_multi.T_profile, result_single.T_profile, atol=1e-4
        )
        np.testing.assert_allclose(
            result_multi.x_profile, result_single.x_profile, atol=1e-4
        )
