"""Tests for UnitOp implementations (Task 2.1.1)."""

import numpy as np
import pytest

from h2iso.equilibrator.exchange import atom_fractions, equilibrium_composition
from h2iso.flowsheet.stream import Stream
from h2iso.flowsheet.unit import (
    ColumnUnit,
    EquilibratorUnit,
    MixerUnit,
    SplitterUnit,
)
from h2iso.mesh.column import Column, ColumnSpec
from h2iso.species import N_SPECIES


@pytest.fixture
def h2_feed():
    """H2-dominant feed stream."""
    z = np.zeros(N_SPECIES)
    z[0] = 0.9975
    z[3] = 0.0025
    return Stream(flow=100.0, composition=z, temperature=22.0, pressure=101325.0)


@pytest.fixture
def mixed_feed():
    """Mixed H2/HD stream."""
    z = np.zeros(N_SPECIES)
    z[0] = 0.90
    z[1] = 0.08
    z[3] = 0.02
    return Stream(flow=60.0, composition=z, temperature=23.0, pressure=101325.0)


class TestColumnUnit:
    """Test ColumnUnit wrapper."""

    def test_single_feed_matches_direct(self, h2_feed):
        """ColumnUnit with single feed should match direct Column.solve()."""
        unit = ColumnUnit(
            name="CD1",
            n_stages=20,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feed_stages=[10],
        )
        outputs = unit.solve({"feed": h2_feed})

        # Direct solve for comparison
        spec = ColumnSpec(
            n_stages=20,
            feed_stage=10,
            feed_flow=100.0,
            feed_composition=h2_feed.composition,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
        )
        direct_result = Column(spec).solve()
        assert direct_result.convergence_info["success"]

        # Outputs should match
        assert "distillate" in outputs
        assert "bottoms" in outputs
        assert outputs["distillate"].flow == pytest.approx(50.0)
        assert outputs["bottoms"].flow == pytest.approx(50.0)
        np.testing.assert_allclose(
            outputs["distillate"].composition,
            direct_result.x_profile[0],
            atol=1e-6,
        )
        np.testing.assert_allclose(
            outputs["bottoms"].composition,
            direct_result.x_profile[-1],
            atol=1e-6,
        )

    def test_multi_feed(self, h2_feed, mixed_feed):
        """ColumnUnit with multiple feeds should converge."""
        unit = ColumnUnit(
            name="CD2",
            n_stages=20,
            pressure=101325.0,
            reflux_ratio=5.0,
            distillate_to_feed=0.5,
            feed_stages=[7, 14],
        )
        outputs = unit.solve({"wds": h2_feed, "recycle": mixed_feed})

        assert "distillate" in outputs
        assert "bottoms" in outputs
        total_flow = h2_feed.flow + mixed_feed.flow
        assert outputs["distillate"].flow + outputs["bottoms"].flow == pytest.approx(
            total_flow
        )


class TestEquilibratorUnit:
    """Test EquilibratorUnit wrapper."""

    def test_matches_direct_call(self, h2_feed):
        """EquilibratorUnit should match direct equilibrium_composition()."""
        unit = EquilibratorUnit(name="EQ1", temperature=25.0)
        outputs = unit.solve({"in": h2_feed})

        # Direct call
        aH, aD, aT = atom_fractions(h2_feed.composition)
        x_eq_direct = equilibrium_composition(aH, aD, aT, T=25.0)

        assert "out" in outputs
        assert outputs["out"].flow == pytest.approx(h2_feed.flow)
        np.testing.assert_allclose(outputs["out"].composition, x_eq_direct, atol=1e-10)

    def test_preserves_flow(self, h2_feed):
        """Equilibrator preserves total flow."""
        unit = EquilibratorUnit(name="EQ2", temperature=25.0)
        outputs = unit.solve({"in": h2_feed})
        assert outputs["out"].flow == pytest.approx(h2_feed.flow)


class TestMixerUnit:
    """Test MixerUnit."""

    def test_two_streams(self, h2_feed, mixed_feed):
        unit = MixerUnit(name="MIX1")
        outputs = unit.solve({"s1": h2_feed, "s2": mixed_feed})

        assert "out" in outputs
        assert outputs["out"].flow == pytest.approx(h2_feed.flow + mixed_feed.flow)
        # Mass conservation per component
        for i in range(N_SPECIES):
            expected = (
                h2_feed.flow * h2_feed.composition[i]
                + mixed_feed.flow * mixed_feed.composition[i]
            )
            actual = outputs["out"].flow * outputs["out"].composition[i]
            assert actual == pytest.approx(expected, abs=1e-10)


class TestSplitterUnit:
    """Test SplitterUnit."""

    def test_equal_split(self, h2_feed):
        unit = SplitterUnit(name="SPL1", ratios={"top": 1.0, "bottom": 1.0})
        outputs = unit.solve({"in": h2_feed})

        assert "top" in outputs
        assert "bottom" in outputs
        assert outputs["top"].flow == pytest.approx(50.0)
        assert outputs["bottom"].flow == pytest.approx(50.0)

    def test_unequal_split(self, h2_feed):
        unit = SplitterUnit(name="SPL2", ratios={"a": 3.0, "b": 1.0})
        outputs = unit.solve({"in": h2_feed})

        assert outputs["a"].flow == pytest.approx(75.0)
        assert outputs["b"].flow == pytest.approx(25.0)

    def test_composition_preserved(self, h2_feed):
        unit = SplitterUnit(name="SPL3", ratios={"a": 2.0, "b": 3.0})
        outputs = unit.solve({"in": h2_feed})

        np.testing.assert_array_equal(outputs["a"].composition, h2_feed.composition)
        np.testing.assert_array_equal(outputs["b"].composition, h2_feed.composition)

    def test_multiple_inputs_raises(self, h2_feed, mixed_feed):
        unit = SplitterUnit(name="SPL4", ratios={"a": 1.0, "b": 1.0})
        with pytest.raises(ValueError, match="1 input"):
            unit.solve({"s1": h2_feed, "s2": mixed_feed})
