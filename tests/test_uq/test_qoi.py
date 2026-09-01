"""Tests for h2iso.uq.qoi — QoI extraction."""

import numpy as np
import pytest

from h2iso.mesh.column import ColumnResult
from h2iso.species import N_SPECIES  # noqa: F401 — just verify import works
from h2iso.species import N_SPECIES as NS
from h2iso.uq.qoi import (
    qoi_convergence,
    qoi_default,
    qoi_labels,
    qoi_n_components,
    qoi_separation_factor,
)


@pytest.fixture
def column_result():
    N = 5
    rng = np.random.default_rng(42)
    x = rng.random((N, 6))
    x = x / x.sum(axis=1, keepdims=True)
    y = rng.random((N, 6))
    y = y / y.sum(axis=1, keepdims=True)
    return ColumnResult(
        T_profile=np.linspace(23, 25, N),
        x_profile=x,
        y_profile=y,
        L_profile=np.full(N, 100.0),
        V_profile=np.full(N, 120.0),
        condenser_duty=-400.0,
        reboiler_duty=410.0,
        convergence_info={"status": "Solve_Succeeded", "success": True},
    )


@pytest.fixture
def flowsheet_result(column_result):
    from h2iso.flowsheet.solver import FlowsheetResult
    from h2iso.flowsheet.stream import Stream

    return FlowsheetResult(
        streams={
            "CD1_distillate": Stream(
                flow=50,
                composition=column_result.x_profile[0],
                temperature=23.0,
                pressure=90000,
            ),
            "CD1_bottoms": Stream(
                flow=30,
                composition=column_result.x_profile[-1],
                temperature=25.0,
                pressure=100000,
            ),
        },
        column_results={"CD1": column_result},
        converged=True,
        iterations=5,
        tear_residual=1e-8,
    )


class TestQoIDefault:
    def test_column_result(self, column_result):
        q = qoi_default(column_result)
        assert q.shape == (2 * NS + 4,)

    def test_flowsheet_result(self, flowsheet_result):
        q = qoi_default(flowsheet_result, column_name="CD1")
        assert q.shape == (2 * NS + 4,)

    def test_flowsheet_auto_pick(self, flowsheet_result):
        q = qoi_default(flowsheet_result)
        assert q.shape == (2 * NS + 4,)

    def test_flowsheet_missing_column(self, flowsheet_result):
        with pytest.raises(KeyError, match="not found"):
            qoi_default(flowsheet_result, column_name="NONEXIST")

    def test_values(self, column_result):
        q = qoi_default(column_result)
        np.testing.assert_allclose(q[:NS], column_result.x_profile[0])
        np.testing.assert_allclose(q[NS : 2 * NS], column_result.x_profile[-1])
        assert q[2 * NS] == pytest.approx(-400.0)
        assert q[2 * NS + 1] == pytest.approx(410.0)
        assert q[2 * NS + 2] == pytest.approx(23.0)
        assert q[2 * NS + 3] == pytest.approx(25.0)

    def test_labels(self):
        labels = qoi_labels("CD1")
        assert len(labels) == qoi_n_components()
        assert labels[0] == "CD1.x_top[H2]"
        assert labels[-1] == "CD1.T_bottom_K"

    def test_labels_no_prefix(self):
        labels = qoi_labels()
        assert labels[0] == "x_top[H2]"

    def test_n_components(self):
        assert qoi_n_components() == 2 * NS + 4


class TestQoISeparationFactor:
    def test_basic(self, column_result):
        alpha = qoi_separation_factor(column_result, "D2", "DT")
        assert alpha.shape == (1,)
        assert alpha[0] > 0
        assert np.isfinite(alpha[0])

    def test_with_flowsheet(self, flowsheet_result):
        alpha = qoi_separation_factor(flowsheet_result, column_name="CD1")
        assert alpha.shape == (1,)


class TestQoIConvergence:
    def test_basic(self, flowsheet_result):
        q = qoi_convergence(flowsheet_result)
        assert q.shape == (3,)
        assert q[0] == 1.0  # converged
        assert q[1] == 5.0  # iterations
        assert q[2] == pytest.approx(1e-8)
