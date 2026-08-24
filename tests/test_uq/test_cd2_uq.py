"""Regression test for CD2 UQ validation case.

Uses a 15-stage column (no continuation) for fast CI execution.
Verifies reproducibility and basic sanity of UQ outputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.uq.qoi import qoi_default
from h2iso.uq.run_cd2 import (
    BASELINE,
    _solve_cd2,
    build_parameter_space,
    make_build_fn,
)
from h2iso.uq.runner import _is_converged, run_samples
from h2iso.uq.sampler import lhs_sample, sobol_sample

N_STAGES = 15
SEED = 42


@pytest.fixture
def space():
    return build_parameter_space()


@pytest.fixture
def build_fn():
    return make_build_fn(n_stages=N_STAGES, use_continuation=False)


class TestParameterSpace:
    def test_four_parameters(self, space):
        assert space.n_params == 4
        assert space.names == ["reflux_ratio", "feed_flow", "z_D2", "pressure"]

    def test_bounds_physical(self, space):
        for p in space.parameters:
            lb, ub = p.bounds
            assert lb < ub
            assert p.mean() > lb
            assert p.mean() < ub


class TestBuildFn:
    def test_produces_spec(self, build_fn):
        params = np.array(
            [
                BASELINE["reflux_ratio"],
                BASELINE["feed_flow"],
                BASELINE["z_D2"],
                BASELINE["pressure"],
            ]
        )
        spec = build_fn(params)
        assert spec.n_stages == N_STAGES
        assert spec.reflux_ratio == pytest.approx(BASELINE["reflux_ratio"])
        assert spec.feed_flow == pytest.approx(BASELINE["feed_flow"])
        assert spec.pressure == pytest.approx(BASELINE["pressure"])

    def test_composition_normalization(self, build_fn):
        params = np.array([15.0, 80.0, 0.98, 95000.0])
        spec = build_fn(params)
        z = spec.feed_composition
        assert z.sum() == pytest.approx(1.0)
        assert z[3] > 0  # D2
        assert z[4] > 0  # DT
        assert z[0] == 0  # H2
        assert z[5] == 0  # T2


class TestSobolRun:
    """Sobol screening with a small n_base on 15-stage column."""

    def test_all_converge(self, space, build_fn, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_cd2)
        monkeypatch.setattr(runner_mod, "_is_converged", _is_converged)

        n_base = 16
        samples = sobol_sample(space.parameters, n_base=n_base, seed=SEED)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_default,
            parallel=1,
        )

        # 15-stage should always converge
        assert summary.fail_rate < 0.05
        assert summary.n_converged >= summary.n_total * 0.95

    def test_reproducible(self, space, build_fn, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_cd2)
        monkeypatch.setattr(runner_mod, "_is_converged", _is_converged)

        n_base = 8
        s1 = sobol_sample(space.parameters, n_base=n_base, seed=SEED)
        s2 = sobol_sample(space.parameters, n_base=n_base, seed=SEED)
        np.testing.assert_array_equal(s1, s2)

        r1 = run_samples(s1, build_fn, qoi_fn=qoi_default, parallel=1)
        r2 = run_samples(s2, build_fn, qoi_fn=qoi_default, parallel=1)
        assert r1.n_converged == r2.n_converged
        if r1.n_converged > 0 and r2.n_converged > 0:
            np.testing.assert_allclose(
                r1.qoi_matrix,
                r2.qoi_matrix,
                rtol=1e-10,
            )


class TestMCSanity:
    """Monte Carlo sanity checks on 15-stage column."""

    def test_mc_all_converge(self, space, build_fn, monkeypatch):
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_cd2)
        monkeypatch.setattr(runner_mod, "_is_converged", _is_converged)

        samples = lhs_sample(space.parameters, n=30, seed=SEED)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_default,
            parallel=1,
        )
        assert summary.fail_rate < 0.05

    def test_d2_purity_positive(self, space, build_fn, monkeypatch):
        """D2 top purity should be positive and < 1."""
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_cd2)
        monkeypatch.setattr(runner_mod, "_is_converged", _is_converged)

        samples = lhs_sample(space.parameters, n=10, seed=SEED)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_default,
            parallel=1,
        )
        if summary.n_converged > 0:
            d2_top = summary.qoi_matrix[:, 3]  # D2 is index 3
            assert np.all(d2_top > 0)
            assert np.all(d2_top < 1.0)

    def test_temperature_range(self, space, build_fn, monkeypatch):
        """All temperatures should be in [14, 35] K (column bounds)."""
        import h2iso.uq.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_solve_config", _solve_cd2)
        monkeypatch.setattr(runner_mod, "_is_converged", _is_converged)

        samples = lhs_sample(space.parameters, n=10, seed=SEED)
        summary = run_samples(
            samples,
            build_fn,
            qoi_fn=qoi_default,
            parallel=1,
        )
        if summary.n_converged > 0:
            # T_top = index 14, T_bot = index 15 in QoI vector
            T_all = np.concatenate(
                [
                    summary.qoi_matrix[:, 14],
                    summary.qoi_matrix[:, 15],
                ]
            )
            assert np.all(T_all > 14.0)
            assert np.all(T_all < 35.0)
