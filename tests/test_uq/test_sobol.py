"""Tests for h2iso.uq.sobol — sensitivity index computation."""

import numpy as np
import pytest

from h2iso.uq.distributions import Parameter
from h2iso.uq.sampler import sobol_sample
from h2iso.uq.sobol import SobolResult, analyze_sobol


@pytest.fixture
def three_params():
    return [
        Parameter("A", "uniform", {"low": 0, "high": 1}),
        Parameter("B", "uniform", {"low": 0, "high": 1}),
        Parameter("C", "uniform", {"low": 0, "high": 1}),
    ]


def _linear_model(samples, coefs):
    """y = coefs . x  (linear, so Sobol S1 ≈ normalized coefs²)."""
    return samples @ np.array(coefs)


class TestAnalyzeSobol:
    def test_linear_model(self, three_params):
        """For a linear model y = a1*x1 + a2*x2 + a3*x3, the first-order
        Sobol indices should be proportional to a_i² / sum(a_j²)."""
        n_base = 128
        samples = sobol_sample(three_params, n_base=n_base, seed=42)

        # Model: x1 dominates, x3 is zero
        coefs = [1.0, 0.3, 0.0]
        y = _linear_model(samples, coefs).reshape(-1, 1)

        result = analyze_sobol(
            three_params,
            samples,
            y,
            qoi_names=["y"],
            n_base=n_base,
            seed=42,
        )

        assert isinstance(result, SobolResult)
        assert result.S1.shape == (3, 1)
        assert result.ST.shape == (3, 1)

        # x1 should have highest S1, x3 should be ~0
        assert result.S1[0, 0] > result.S1[1, 0]
        assert result.S1[2, 0] < 0.05

        # For a purely linear (additive) model, S1 ≈ ST
        np.testing.assert_allclose(result.S1[:, 0], result.ST[:, 0], atol=0.1)

    def test_top_k(self, three_params):
        n_base = 64
        samples = sobol_sample(three_params, n_base=n_base, seed=42)
        coefs = [1.0, 0.1, 0.5]
        y = _linear_model(samples, coefs).reshape(-1, 1)

        result = analyze_sobol(
            three_params,
            samples,
            y,
            n_base=n_base,
            seed=42,
        )

        top2 = result.top_k(k=2, metric="ST")
        assert "A" in top2
        assert "C" in top2
        assert "B" not in top2

    def test_to_dict(self, three_params):
        n_base = 32
        samples = sobol_sample(three_params, n_base=n_base, seed=42)
        y = samples[:, 0:1]

        result = analyze_sobol(
            three_params,
            samples,
            y,
            n_base=n_base,
            seed=42,
        )
        d = result.to_dict()
        assert "parameter_names" in d
        assert "qoi_names" in d
        assert "S1" in d
        assert "ST" in d
        assert len(d["S1"]) == 3

    def test_too_few_samples_raises(self, three_params):
        n_base = 32
        samples = sobol_sample(three_params, n_base=n_base, seed=42)
        expected = n_base * (2 * 3 + 2)

        # Only pass half the samples
        y = np.random.default_rng(0).random((expected // 2, 1))

        with pytest.raises(ValueError, match="Expected.*valid samples"):
            analyze_sobol(
                three_params,
                samples[: expected // 2],
                y,
                n_base=n_base,
                seed=42,
            )

    def test_multi_qoi(self, three_params):
        n_base = 64
        samples = sobol_sample(three_params, n_base=n_base, seed=42)

        # Two QoIs with different parameter sensitivity
        y1 = _linear_model(samples, [1, 0, 0]).reshape(-1, 1)
        y2 = _linear_model(samples, [0, 0, 1]).reshape(-1, 1)
        Y = np.hstack([y1, y2])

        result = analyze_sobol(
            three_params,
            samples,
            Y,
            qoi_names=["y1", "y2"],
            n_base=n_base,
            seed=42,
        )

        assert result.S1.shape == (3, 2)
        # y1: A dominates; y2: C dominates
        assert result.S1[0, 0] > result.S1[2, 0]  # A > C for y1
        assert result.S1[2, 1] > result.S1[0, 1]  # C > A for y2
