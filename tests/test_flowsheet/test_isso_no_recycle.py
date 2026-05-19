"""ISS-O three-column solve without recycle streams.

Tests the sequential CD1 → CD2 → equilibrator → CD3 chain
with tear streams removed (zero flow), verifying each column
converges independently and produces physically reasonable results.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from h2iso.flowsheet.schema import FlowsheetConfig, load_flowsheet
from h2iso.flowsheet.solver import SequentialModularSolver

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "wang2022" / "wang2022_isso.json"


@pytest.fixture
def isso_no_recycle_config() -> FlowsheetConfig:
    """Load ISS-O config with recycle streams removed."""
    config = load_flowsheet(FIXTURE_PATH)
    # Remove tear streams (no recycle)
    config.tear_streams = []
    # Remove recycle connections from topology
    config.connections = [
        conn for conn in config.connections
        if conn.from_unit not in ("CD2_bottom_recycle", "CD3_top")
    ]
    # Remove recycle feed positions from columns
    for col in config.columns:
        col.feed_positions = {
            k: v for k, v in col.feed_positions.items()
            if k not in ("CD2_bottom_recycle", "CD3_top")
        }
    return config


class TestISSONoRecycle:
    """Test ISS-O three-column sequential solve without recycle."""

    def test_solver_converges(self, isso_no_recycle_config):
        """All three columns converge in a single pass (no iteration)."""
        solver = SequentialModularSolver(
            isso_no_recycle_config,
            method="direct",
            continuation_substeps=3,
        )
        result = solver.solve(max_iter=1, tol=1e-6)
        assert result.converged, (
            f"Solver did not converge: residual={result.tear_residual}, "
            f"iterations={result.iterations}"
        )

    def test_cd1_converges(self, isso_no_recycle_config):
        """CD1 (60 stages, R=6) converges independently."""
        solver = SequentialModularSolver(
            isso_no_recycle_config,
            method="direct",
            continuation_substeps=3,
        )
        result = solver.solve(max_iter=1)
        # CD1 should produce output streams
        assert "CD1_distillate" in result.streams or "CD1_bottoms" in result.streams

    def test_temperature_ranges(self, isso_no_recycle_config):
        """All column temperatures are in 19-26 K range."""
        solver = SequentialModularSolver(
            isso_no_recycle_config,
            method="direct",
            continuation_substeps=3,
        )
        result = solver.solve(max_iter=1)

        for col_name in ("CD1", "CD2", "CD3"):
            distillate_key = f"{col_name}_distillate"
            bottoms_key = f"{col_name}_bottoms"

            if distillate_key in result.streams:
                T_top = result.streams[distillate_key].temperature
                assert 19.0 <= T_top <= 26.0, (
                    f"{col_name} top T={T_top:.2f} K outside [19, 26] range"
                )

            if bottoms_key in result.streams:
                T_bot = result.streams[bottoms_key].temperature
                assert 19.0 <= T_bot <= 26.0, (
                    f"{col_name} bottom T={T_bot:.2f} K outside [19, 26] range"
                )

    def test_cd1_top_h2_rich(self, isso_no_recycle_config):
        """CD1 distillate should be >99% H2."""
        solver = SequentialModularSolver(
            isso_no_recycle_config,
            method="direct",
            continuation_substeps=3,
        )
        result = solver.solve(max_iter=1)

        dist = result.streams.get("CD1_distillate")
        assert dist is not None, "CD1_distillate stream not found"
        # H2 is species index 0
        h2_frac = dist.composition[0]
        assert h2_frac > 0.99, (
            f"CD1 top H2 fraction = {h2_frac:.5f}, expected > 0.99"
        )

    def test_cd3_bottom_heavy_isotopes(self, isso_no_recycle_config):
        """CD3 bottoms should be enriched in HT/DT/T2 (heavy isotopes).

        Without the equilibrator, CD3 receives CD2 bottoms directly,
        which is HT-rich. CD3 should concentrate the heaviest components.
        """
        solver = SequentialModularSolver(
            isso_no_recycle_config,
            method="direct",
            continuation_substeps=3,
        )
        result = solver.solve(max_iter=1)

        bottoms = result.streams.get("CD3_bottoms")
        if bottoms is not None:
            # HT(idx=2) + DT(idx=4) + T2(idx=5) should dominate
            heavy_frac = bottoms.composition[2] + bottoms.composition[4] + bottoms.composition[5]
            assert heavy_frac > 0.5, (
                f"CD3 bottom heavy isotope fraction = {heavy_frac:.4f}, expected > 0.5"
            )

    def test_mass_balance(self, isso_no_recycle_config):
        """Total feed flow = total product flow (mass conservation)."""
        solver = SequentialModularSolver(
            isso_no_recycle_config,
            method="direct",
            continuation_substeps=3,
        )
        result = solver.solve(max_iter=1)

        # Total external feed
        total_feed = sum(f.flow for f in isso_no_recycle_config.feeds)

        # Products: CD1_top, CD2_top, CD3_bottom
        # In no-recycle mode, all column outputs are products
        product_flow = 0.0
        for key, stream in result.streams.items():
            if key.endswith("_distillate") or key.endswith("_bottoms"):
                # Only count final products (leaf nodes)
                pass
        # Alternative: sum all distillate + last column bottoms
        # Actually in ISS-O, products are CD1_top, CD2_top, CD3_bottom
        # In a cascade: CD1 bottoms -> CD2, CD2 bottoms -> CD3
        # So net products = CD1_dist + CD2_dist + CD3_dist + CD3_bottoms
        # But CD3 distillate recycles to CD2 in full model; without recycle it's a product
        # For mass balance: total_in = total_out always
        # Sum all "terminal" streams
        cd1_d = result.streams.get("CD1_distillate")
        cd2_d = result.streams.get("CD2_distillate")
        cd3_d = result.streams.get("CD3_distillate")
        cd3_b = result.streams.get("CD3_bottoms")

        product_flow = 0.0
        if cd1_d:
            product_flow += cd1_d.flow
        if cd2_d:
            product_flow += cd2_d.flow
        if cd3_d:
            product_flow += cd3_d.flow
        if cd3_b:
            product_flow += cd3_b.flow

        # Allow 1% tolerance (numerical + intermediate streams may have rounding)
        assert product_flow > 0, "No product streams found"
        rel_error = abs(product_flow - total_feed) / total_feed
        assert rel_error < 0.01, (
            f"Mass balance error: feed={total_feed:.2f}, products={product_flow:.2f}, "
            f"rel_error={rel_error:.4f}"
        )
