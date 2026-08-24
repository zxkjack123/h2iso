"""Regression test for ISS-O flowsheet UQ validation case.

Uses reduced 8-stage columns in no-recycle (fast) mode for CI speed
(~0.3 s/solve). Verifies parameter space construction, build_fn output,
and basic UQ study convergence.
"""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.uq.qoi import (
    qoi_isso_compact,
    qoi_isso_compact_labels,
    qoi_isso_labels,
)
from h2iso.uq.run_isso import (
    _solve_isso,
    build_parameter_space,
    make_build_fn,
    run_uq,
)
from h2iso.uq.runner import run_samples


class TestParameterSpace:
    def test_fast_mode_11_params(self):
        space = build_parameter_space(full=False)
        assert space.n_params == 11
        for col in ("CD1", "CD2", "CD3"):
            assert f"{col}.R" in space.names
            assert f"{col}.DF" in space.names
            assert f"{col}.P" in space.names
        assert "feed.WDS" in space.names
        assert "feed.TES" in space.names

    def test_full_mode_8_params(self):
        space = build_parameter_space(full=True)
        assert space.n_params == 8
        assert "CD1.DF" not in space.names  # D/F only in fast mode

    def test_bounds_physical(self):
        for full in (True, False):
            space = build_parameter_space(full)
            for p in space.parameters:
                lb, ub = p.bounds
                assert lb < ub
                m = p.mean()
                assert lb <= m <= ub or abs(m - lb) < 1e-10 or abs(m - ub) < 1e-10


class TestBuildFn:
    def test_fast_produces_flowsheet(self):
        build_fn = make_build_fn(full=False, n_stages=8)
        space = build_parameter_space(full=False)
        params = np.array([p.mean() for p in space.parameters])
        config = build_fn(params)

        assert len(config.columns) == 3
        assert config.columns[0].n_stages == 8
        assert not config.tear_streams  # no recycle in fast mode

    def test_column_scaling(self):
        build_fn = make_build_fn(full=False, n_stages=8)
        space = build_parameter_space(full=False)
        params = np.array([p.mean() for p in space.parameters])
        config = build_fn(params)
        for col in config.columns:
            assert col.n_stages == 8

    def test_reproducible(self):
        build_fn = make_build_fn(full=False, n_stages=8)
        space = build_parameter_space(full=False)
        params = np.array([p.mean() for p in space.parameters])
        c1 = build_fn(params)
        c2 = build_fn(params)
        for col1, col2 in zip(c1.columns, c2.columns):
            assert col1.reflux_ratio == col2.reflux_ratio
            assert col1.n_stages == col2.n_stages

    def test_parameter_gets_applied(self):
        build_fn = make_build_fn(full=False, n_stages=10)
        space = build_parameter_space(full=False)
        means = [p.mean() for p in space.parameters]
        params = np.array(means)
        # Change CD1.R to a value far from mean
        params[0] = 10.0  # CD1.R
        config = build_fn(params)
        assert config.columns[0].reflux_ratio == pytest.approx(10.0)


class TestQoIIsso:
    def test_product_labels_shape(self):
        labels = qoi_isso_labels()
        # Each column: 6 (x_top) + 6 (x_bot) + 2 (Q) + 2 (T) + 2 (F) = 18
        assert len(labels) == 3 * 18

    def test_compact_labels(self):
        labels = qoi_isso_compact_labels()
        assert len(labels) == 13
        assert labels[0] == "CD1_top_H2"
        assert labels[-1] == "converged"


class TestIssoMCSanity:
    """Small MC run on 8-stage no-recycle ISS-O."""

    def test_mc_all_converge(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_isso)

        space = build_parameter_space(full=False)
        build_fn = make_build_fn(full=False, n_stages=8)

        from h2iso.uq.sampler import lhs_sample

        samples = lhs_sample(space.parameters, n=8, seed=42)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_isso_compact,
            parallel=1,
            solve_kwargs={"method": "direct", "max_iter": 1},
        )
        assert summary.n_converged == 8
        assert summary.fail_rate == 0.0

    def test_h2_purity_positive(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_isso)

        space = build_parameter_space(full=False)
        build_fn = make_build_fn(full=False, n_stages=8)

        from h2iso.uq.sampler import lhs_sample

        samples = lhs_sample(space.parameters, n=4, seed=42)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_isso_compact,
            parallel=1,
            solve_kwargs={"method": "direct", "max_iter": 1},
        )
        assert summary.n_converged == 4
        qmat = summary.qoi_matrix
        # CD1 top H2 (index 0) and CD2 top H2 (index 1) should be positive
        assert np.all(qmat[:, 0] > 0.9)  # CD1 top H2 > 90%
        assert np.all(qmat[:, 1] > 0.9)  # CD2 top H2 > 90%

    def test_temperature_range(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_isso)

        space = build_parameter_space(full=False)
        build_fn = make_build_fn(full=False, n_stages=8)

        from h2iso.uq.sampler import lhs_sample

        samples = lhs_sample(space.parameters, n=4, seed=42)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_isso_compact,
            parallel=1,
            solve_kwargs={"method": "direct", "max_iter": 1},
        )
        qmat = summary.qoi_matrix
        # Temperature columns: 3,4=CD1_T_top/bot, 5,6=CD2, 7,8=CD3
        for j in (3, 4, 5, 6, 7, 8):
            assert np.all(qmat[:, j] > 19.0)
            assert np.all(qmat[:, j] < 26.0)

    def test_reproducible(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_isso)

        space = build_parameter_space(full=False)
        build_fn = make_build_fn(full=False, n_stages=8)

        from h2iso.uq.sampler import lhs_sample

        s1 = lhs_sample(space.parameters, n=3, seed=42)
        s2 = lhs_sample(space.parameters, n=3, seed=42)
        np.testing.assert_array_equal(s1, s2)

        r1 = run_samples(
            s1,
            build_fn,
            qoi_fn=qoi_isso_compact,
            parallel=1,
            solve_kwargs={"method": "direct", "max_iter": 1},
        )
        r2 = run_samples(
            s2,
            build_fn,
            qoi_fn=qoi_isso_compact,
            parallel=1,
            solve_kwargs={"method": "direct", "max_iter": 1},
        )
        assert r1.n_converged == r2.n_converged
        np.testing.assert_allclose(r1.qoi_matrix, r2.qoi_matrix, rtol=1e-10)


class TestIssoSobolScreening:
    """Small Sobol run on 8-stage no-recycle ISS-O."""

    def test_sobol_all_converge(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_isso)

        space = build_parameter_space(full=False)
        build_fn = make_build_fn(full=False, n_stages=8)

        from h2iso.uq.sampler import sobol_sample

        n_base = 4
        samples = sobol_sample(space.parameters, n_base=n_base, seed=42)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_isso_compact,
            parallel=1,
            solve_kwargs={"method": "direct", "max_iter": 1},
        )
        assert summary.fail_rate < 0.05

    def test_run_uq_function(self):
        """Test the top-level run_uq() with tiny sample sizes."""
        sobol_result, sobol_summary, mc_summary = run_uq(
            full=False,
            n_stages=8,
            sobol_n_base=4,
            mc_n=5,
            seed=42,
            parallel=1,
            output_dir="uq_runs/isso/test",
        )
        assert sobol_summary.n_total > 0
        assert mc_summary.n_total == 5
        assert mc_summary.n_converged == 5
