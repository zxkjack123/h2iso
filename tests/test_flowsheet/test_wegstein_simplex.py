"""Task 4.3 property tests: Wegstein update preserves composition simplex."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from h2iso.flowsheet.schema import (
    ColumnConfig,
    Connection,
    FeedConfig,
    FlowsheetConfig,
)
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.flowsheet.stream import Stream
from h2iso.species import N_SPECIES


def _make_simplex(rng: np.random.Generator) -> np.ndarray:
    """Random point on the 6-species simplex."""
    raw = rng.uniform(0.01, 1.0, size=N_SPECIES)
    return raw / raw.sum()


def _make_solver() -> SequentialModularSolver:
    feed = FeedConfig(
        name="F1",
        flow=10.0,
        composition=[1 / N_SPECIES] * N_SPECIES,
        target_column="C1",
        feed_stage=5,
    )
    col = ColumnConfig(
        name="C1",
        n_stages=10,
        reflux_ratio=2.0,
        distillate_to_feed=0.5,
        feed_positions={"F1": 5},
        pressure=101325.0,
    )
    cfg = FlowsheetConfig(
        feeds=[feed],
        columns=[col],
        equilibrators=[],
        connections=[Connection(from_unit="F1", to_unit="C1", stage=5)],
        products={"D": "distillate of C1"},
        tear_streams=[],
    )
    return SequentialModularSolver(cfg, method="wegstein")


class TestMethodValidation:
    def test_invalid_method_capitalized_raises(self):
        feed = FeedConfig(
            name="F1",
            flow=10.0,
            composition=[1 / N_SPECIES] * N_SPECIES,
            target_column="C1",
            feed_stage=5,
        )
        col = ColumnConfig(
            name="C1",
            n_stages=10,
            reflux_ratio=2.0,
            distillate_to_feed=0.5,
            feed_positions={"F1": 5},
            pressure=101325.0,
        )
        cfg = FlowsheetConfig(
            feeds=[feed],
            columns=[col],
            equilibrators=[],
            connections=[Connection(from_unit="F1", to_unit="C1", stage=5)],
            products={"D": "distillate"},
            tear_streams=[],
        )
        with pytest.raises(ValueError, match="method must be"):
            SequentialModularSolver(cfg, method="Wegstein")

    def test_unknown_method_raises(self):
        feed = FeedConfig(
            name="F1",
            flow=10.0,
            composition=[1 / N_SPECIES] * N_SPECIES,
            target_column="C1",
            feed_stage=5,
        )
        col = ColumnConfig(
            name="C1",
            n_stages=10,
            reflux_ratio=2.0,
            distillate_to_feed=0.5,
            feed_positions={"F1": 5},
            pressure=101325.0,
        )
        cfg = FlowsheetConfig(
            feeds=[feed],
            columns=[col],
            equilibrators=[],
            connections=[Connection(from_unit="F1", to_unit="C1", stage=5)],
            products={"D": "distillate"},
            tear_streams=[],
        )
        with pytest.raises(ValueError, match="method must be"):
            SequentialModularSolver(cfg, method="aitken")


class TestWegsteinSimplexPreservation:
    """After Wegstein/direct-substitution updates the output Stream must always
    satisfy the composition simplex (>=0 and sum-to-one within tolerance)."""

    @given(seed=st.integers(min_value=0, max_value=2**31 - 1))
    @settings(max_examples=25, deadline=None)
    def test_single_update_preserves_simplex(self, seed):
        rng = np.random.default_rng(seed)
        solver = _make_solver()

        x_stream = Stream(
            flow=10.0,
            composition=_make_simplex(rng),
            temperature=25.0,
            pressure=101325.0,
        )
        g_stream = Stream(
            flow=10.0 + rng.uniform(-1.0, 1.0),
            composition=_make_simplex(rng),
            temperature=25.0,
            pressure=101325.0,
        )

        # Two-iteration warmup (first call falls back to direct substitution).
        x_prev = {"S": np.concatenate([[x_stream.flow], x_stream.composition])}
        g_prev = {"S": np.concatenate([[g_stream.flow], g_stream.composition])}

        # Build a fresh perturbed pair to trigger the Wegstein branch.
        x2 = Stream(
            flow=g_stream.flow,
            composition=g_stream.composition,
            temperature=25.0,
            pressure=101325.0,
        )
        g2_comp = _make_simplex(rng)
        g2 = Stream(
            flow=g_stream.flow + rng.uniform(-1.0, 1.0),
            composition=g2_comp,
            temperature=25.0,
            pressure=101325.0,
        )

        updated = solver._wegstein_update(
            {"S": x2}, {"S": g2}, x_prev, g_prev
        )
        out = updated["S"]
        assert (out.composition >= 0).all()
        assert abs(out.composition.sum() - 1.0) < 1e-12

    def test_100_iterations_preserve_simplex(self):
        """Repeated Wegstein updates on randomised pairs never drift off-simplex."""
        rng = np.random.default_rng(20260102)
        solver = _make_solver()

        x = Stream(flow=10.0, composition=_make_simplex(rng),
                   temperature=25.0, pressure=101325.0)
        x_prev = {"S": np.concatenate([[x.flow], x.composition])}
        g_prev = {"S": np.concatenate([[x.flow], x.composition])}

        for _ in range(100):
            g_comp = _make_simplex(rng)
            g = Stream(flow=10.0 + rng.uniform(-0.5, 0.5),
                       composition=g_comp,
                       temperature=25.0, pressure=101325.0)
            updated = solver._wegstein_update({"S": x}, {"S": g}, x_prev, g_prev)
            out = updated["S"]
            assert (out.composition >= 0).all(), \
                f"Negative composition emerged: {out.composition}"
            assert abs(out.composition.sum() - 1.0) < 1e-12, \
                f"Simplex broken: sum={out.composition.sum()}"
            # Advance state
            x_prev = dict(solver._last_x_prev)
            g_prev = dict(solver._last_g_prev)
            x = out
