"""ISS-I four-column full validation with recycle streams.

Tests the complete ISS-I (inner fuel cycle) system from Wang 2022:
- TEP (22.32 mol/h) fed to CD1 stage 50
- NBI (80.357 mol/h) fed to CD2 stage 37
- CD1 bottom + CD2 bottom → CD3 (stages 45 and 15)
- CD1 top → equilibrator 2 (E2) → CD4 stage 55
- CD3 top → equilibrator 1 (E1) → CD1 stage 72 (tear recycle)
- CD4 top (HD exhaust) and CD4 bottom (D2 product)
- CD2 top (D2 product) and CD3 bottom (T2 product)

Validates against Wang 2022 Table 1, 5, 8, 9, 10 reference data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("casadi")

from h2iso.flowsheet.schema import load_flowsheet
from h2iso.flowsheet.solver import SequentialModularSolver

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "wang2022" / "wang2022_issi.json"


@pytest.fixture(scope="module")
def issi_full_result():
    """Load and solve full ISS-I system with recycles."""
    config = load_flowsheet(FIXTURE_PATH)
    solver = SequentialModularSolver(
        config,
        method="wegstein",
        continuation_substeps=3,
    )
    result = solver.solve(max_iter=50, tol=1e-4)
    return result


class TestISSIFullConvergence:
    """Test that the full ISS-I system converges."""

    def test_converges_within_50_iterations(self, issi_full_result):
        """SM solver converges with E1-CD1 tear stream < 50 iterations."""
        assert issi_full_result.converged, (
            f"ISS-I did not converge: residual={issi_full_result.tear_residual:.6f}, "
            f"iterations={issi_full_result.iterations}"
        )
        assert issi_full_result.iterations <= 50

    def test_tear_residual_below_tolerance(self, issi_full_result):
        """Tear stream residual is below convergence tolerance."""
        assert issi_full_result.tear_residual < 1e-4


class TestISSIFullTemperatures:
    """Validate column temperatures against Wang 2022 Table 8."""

    REF_TEMPS = {
        "CD1": {"top": 23.3745, "bottom": 24.5114},
        "CD2": {"top": 23.4102, "bottom": 24.4085},
        "CD3": {"top": 24.1152, "bottom": 24.6124},
        "CD4": {"top": 21.8277, "bottom": 23.7856},
    }

    def test_temperatures_in_physical_range(self, issi_full_result):
        """All temperatures between 20 K and 26 K."""
        for col_name in ("CD1", "CD2", "CD3", "CD4"):
            dist_key = f"{col_name}_distillate"
            bot_key = f"{col_name}_bottoms"
            if dist_key in issi_full_result.streams:
                T = issi_full_result.streams[dist_key].temperature
                assert 20.0 <= T <= 26.0, f"{col_name} top T={T:.2f} K"
            if bot_key in issi_full_result.streams:
                T = issi_full_result.streams[bot_key].temperature
                assert 20.0 <= T <= 26.0, f"{col_name} bottom T={T:.2f} K"

    def test_temperature_deviation_within_2K(self, issi_full_result):
        """Temperature deviations from Wang 2022 are < 2 K."""
        for col_name, ref_temps in self.REF_TEMPS.items():
            dist_key = f"{col_name}_distillate"
            bot_key = f"{col_name}_bottoms"

            if dist_key in issi_full_result.streams:
                T_top = issi_full_result.streams[dist_key].temperature
                assert abs(T_top - ref_temps["top"]) < 2.0, (
                    f"{col_name} top: T={T_top:.3f} K vs ref={ref_temps['top']:.4f} K"
                )

            if bot_key in issi_full_result.streams:
                T_bot = issi_full_result.streams[bot_key].temperature
                assert abs(T_bot - ref_temps["bottom"]) < 2.0, (
                    f"{col_name} bottom: T={T_bot:.3f} K vs ref={ref_temps['bottom']:.4f} K"
                )


class TestISSIFullProducts:
    """Validate product compositions against Wang 2022 Table 9."""

    def test_cd2_top_d2_purity(self, issi_full_result):
        """CD2 distillate is > 99.9% D2 (ref: 99.9736%)."""
        dist = issi_full_result.streams.get("CD2_distillate")
        assert dist is not None, "CD2_distillate not in results"
        d2_frac = dist.composition[3]  # D2 is index 3
        assert d2_frac > 0.999, f"CD2 top D2 = {d2_frac:.5f}, expected > 0.999"

    def test_cd3_bottom_t2_purity(self, issi_full_result):
        """CD3 bottom is > 90% T2 (ref: 93.3565%)."""
        bot = issi_full_result.streams.get("CD3_bottoms")
        assert bot is not None, "CD3_bottoms not in results"
        t2_frac = bot.composition[5]  # T2 is index 5
        assert t2_frac > 0.90, f"CD3 bottom T2 = {t2_frac:.5f}, expected > 0.90"

    def test_cd4_top_hd_rich(self, issi_full_result):
        """CD4 distillate is > 95% HD (ref: 99.3198%)."""
        dist = issi_full_result.streams.get("CD4_distillate")
        assert dist is not None, "CD4_distillate not in results"
        hd_frac = dist.composition[1]  # HD is index 1
        assert hd_frac > 0.95, f"CD4 top HD = {hd_frac:.5f}, expected > 0.95"

    def test_cd4_bottom_d2_purity(self, issi_full_result):
        """CD4 bottom is > 90% D2 (ref: 95.7342%)."""
        bot = issi_full_result.streams.get("CD4_bottoms")
        assert bot is not None, "CD4_bottoms not in results"
        d2_frac = bot.composition[3]  # D2 is index 3
        assert d2_frac > 0.90, f"CD4 bottom D2 = {d2_frac:.5f}, expected > 0.90"


class TestISSIFullMassBalance:
    """Validate global mass conservation."""

    def test_mass_balance(self, issi_full_result):
        """Total feed flow = total product flow within 0.1%."""
        config = load_flowsheet(FIXTURE_PATH)
        total_feed = sum(f.flow for f in config.feeds)  # TEP(22.32) + NBI(80.357) = 102.677 mol/h

        # In ISS-I: products are CD2_distillate, CD3_bottoms, CD4_distillate, CD4_bottoms
        cd2_d = issi_full_result.streams.get("CD2_distillate")
        cd3_b = issi_full_result.streams.get("CD3_bottoms")
        cd4_d = issi_full_result.streams.get("CD4_distillate")
        cd4_b = issi_full_result.streams.get("CD4_bottoms")

        product_flow = 0.0
        for stream in (cd2_d, cd3_b, cd4_d, cd4_b):
            if stream:
                product_flow += stream.flow

        assert product_flow > 0, "No product streams found"
        rel_error = abs(product_flow - total_feed) / total_feed
        assert rel_error < 0.001, (
            f"Mass balance: feed={total_feed:.3f}, products={product_flow:.3f}, "
            f"rel_error={rel_error:.6f}"
        )
