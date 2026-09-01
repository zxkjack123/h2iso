"""Tests for h2iso.uq.distributions.Parameter."""

import numpy as np
import pytest
from scipy import stats

from h2iso.uq.distributions import Parameter


class TestParameterCreation:
    def test_normal(self):
        p = Parameter("test", "normal", {"mu": 10.0, "sigma": 0.5})
        assert p.distribution == "normal"
        assert p.mean() == pytest.approx(10.0)

    def test_uniform(self):
        p = Parameter("test", "uniform", {"low": 5.0, "high": 15.0})
        assert p.distribution == "uniform"
        assert p.mean() == pytest.approx(10.0)

    def test_lognormal(self):
        p = Parameter("test", "lognormal", {"mu": 0.0, "sigma": 0.5})
        assert p.distribution == "lognormal"
        # lognorm(s=0.5, scale=exp(0)) has mean = exp(0 + 0.5²/2) = exp(0.125)
        assert p.mean() == pytest.approx(np.exp(0.125), rel=1e-6)

    def test_invalid_distribution(self):
        with pytest.raises(ValueError, match="distribution must be one of"):
            Parameter("test", "exponential", {"lam": 1.0})

    def test_bounds(self):
        p = Parameter(
            "test",
            "normal",
            {"mu": 10.0, "sigma": 5.0},
            bounds=(8.0, 12.0),
        )
        assert p.mean() == pytest.approx(10.0)
        rng = np.random.default_rng(42)
        samples = p.sample(1000, rng)
        assert samples.min() >= 8.0
        assert samples.max() <= 12.0

    def test_serialization(self):
        p = Parameter(
            "R",
            "normal",
            {"mu": 15, "sigma": 0.3},
            bounds=(10, 20),
            description="reflux ratio",
        )
        d = p.to_dict()
        p2 = Parameter.from_dict(d)
        assert p2.name == p.name
        assert p2.distribution == p.distribution
        assert p2.params == p.params
        assert p2.bounds == p.bounds
        assert p2.description == p.description


class TestParameterSampling:
    def test_reproducible(self):
        p = Parameter("R", "normal", {"mu": 15, "sigma": 0.3})
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        s1 = p.sample(100, rng1)
        s2 = p.sample(100, rng2)
        np.testing.assert_array_equal(s1, s2)

    def test_sample_shape(self):
        p = Parameter("R", "uniform", {"low": 10, "high": 20})
        rng = np.random.default_rng(0)
        s = p.sample(50, rng)
        assert s.shape == (50,)

    def test_ppf_shape(self):
        p = Parameter("R", "normal", {"mu": 15, "sigma": 0.3})
        q = np.linspace(0.01, 0.99, 20)
        vals = p.ppf(q)
        assert vals.shape == (20,)

    def test_ppf_monotonic(self):
        p = Parameter("R", "lognormal", {"mu": 0.0, "sigma": 0.5})
        q = np.linspace(0.05, 0.95, 50)
        vals = p.ppf(q)
        assert np.all(np.diff(vals) > 0)

    def test_ppf_bounds_clip(self):
        p = Parameter(
            "P",
            "normal",
            {"mu": 100, "sigma": 50},
            bounds=(80, 120),
        )
        q = np.array([0.0, 0.001, 0.5, 0.999, 1.0])
        vals = p.ppf(q)
        assert vals.min() >= 80.0
        assert vals.max() <= 120.0

    def test_uniform_ppf_matches_scipy(self):
        p = Parameter("u", "uniform", {"low": 3, "high": 7})
        q = np.array([0.25, 0.5, 0.75])
        vals = p.ppf(q)
        expected = stats.uniform.ppf(q, loc=3, scale=4)
        np.testing.assert_allclose(vals, expected)
