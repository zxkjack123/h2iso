"""Test h2iso ISS-I runner for parity."""

import pytest

from h2iso.parity.h2iso_runner import run_h2iso_iss_i


@pytest.fixture(scope="module")
def tc1_result():
    return run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=6, max_iter=20)


class TestH2isoRunner:
    def test_tc1_converges(self, tc1_result):
        r = tc1_result
        assert r["converged"]

    def test_tc1_products_positive(self, tc1_result):
        r = tc1_result
        for stream in ("WDS", "SDST2"):
            for elem in ("H", "D", "T"):
                v = r["products"][stream][elem]
                assert v > -1e-6, f"{stream}.{elem}={v:.2e}, expected non-negative"

    def test_tc1_sdst2_t_positive(self, tc1_result):
        r = tc1_result
        assert r["products"]["SDST2"]["T"] > 0


@pytest.mark.slow
class TestH2isoRunnerSlow:
    def test_tc1_10stage(self):
        r = run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=10, max_iter=30)
        assert r["converged"]

    def test_all_cases_10stage(self):
        for H, D, T in [
            (10.0, 50.0, 100.0),
            (50.0, 50.0, 50.0),
            (5.0, 10.0, 150.0),
        ]:
            r = run_h2iso_iss_i(H, D, T, n_stages=10, max_iter=30)
            assert r["converged"], f"H={H} D={D} T={T} not converged"
