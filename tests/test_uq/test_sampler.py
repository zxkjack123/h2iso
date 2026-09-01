"""Tests for h2iso.uq.sampler."""

import numpy as np
import pytest

from h2iso.uq.distributions import Parameter
from h2iso.uq.sampler import lhs_sample, random_sample, sobol_sample


@pytest.fixture
def two_params():
    return [
        Parameter("R", "normal", {"mu": 15, "sigma": 0.3}, bounds=(10, 20)),
        Parameter("F", "uniform", {"low": 70, "high": 90}),
    ]


class TestLHS:
    def test_shape(self, two_params):
        s = lhs_sample(two_params, n=100, seed=42)
        assert s.shape == (100, 2)

    def test_reproducible(self, two_params):
        s1 = lhs_sample(two_params, n=50, seed=42)
        s2 = lhs_sample(two_params, n=50, seed=42)
        np.testing.assert_array_equal(s1, s2)

    def test_different_seeds(self, two_params):
        s1 = lhs_sample(two_params, n=50, seed=1)
        s2 = lhs_sample(two_params, n=50, seed=2)
        assert not np.allclose(s1, s2)

    def test_bounds_respected(self, two_params):
        s = lhs_sample(two_params, n=200, seed=0)
        assert s[:, 0].min() >= 10
        assert s[:, 0].max() <= 20
        assert s[:, 1].min() >= 70
        assert s[:, 1].max() <= 90

    def test_stratification(self):
        """LHS should have better space-filling than plain MC."""
        param = [Parameter("u", "uniform", {"low": 0, "high": 1})]
        s_lhs = lhs_sample(param, n=20, seed=42)
        s_mc = random_sample(param, n=20, seed=42)
        hist_lhs, _ = np.histogram(s_lhs[:, 0], bins=10, range=(0, 1))
        assert np.all(hist_lhs == 2)
        hist_mc, _ = np.histogram(s_mc[:, 0], bins=10, range=(0, 1))
        assert not np.all(hist_mc == 2)


class TestSobolSample:
    def test_shape(self, two_params):
        s = sobol_sample(two_params, n_base=16, seed=42)
        K = 2
        # calc_second_order=False -> N * (K + 2) rows
        expected = 16 * (K + 2)
        assert s.shape == (expected, K)

    def test_reproducible(self, two_params):
        s1 = sobol_sample(two_params, n_base=8, seed=42)
        s2 = sobol_sample(two_params, n_base=8, seed=42)
        np.testing.assert_array_equal(s1, s2)

    def test_bounds(self, two_params):
        s = sobol_sample(two_params, n_base=8, seed=0)
        assert s[:, 0].min() >= 10
        assert s[:, 0].max() <= 20
        assert s[:, 1].min() >= 70
        assert s[:, 1].max() <= 90

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            sobol_sample([], n_base=8)


class TestRandomSample:
    def test_shape(self, two_params):
        s = random_sample(two_params, n=100, seed=42)
        assert s.shape == (100, 2)

    def test_reproducible(self, two_params):
        s1 = random_sample(two_params, n=50, seed=42)
        s2 = random_sample(two_params, n=50, seed=42)
        np.testing.assert_array_equal(s1, s2)
