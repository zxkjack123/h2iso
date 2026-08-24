"""Integration test: ISS-I full flowsheet with recycles.

Validates the ISS-I three-column cascade (CD1 → CD2 → E1/CD3 → E2 → CD1)
with two equilibrators and two tear streams.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from h2iso.flowsheet.schema import FlowsheetConfig, load_flowsheet, validate_topology
from h2iso.flowsheet.solver import SequentialModularSolver

FIXTURE = Path(__file__).parent.parent / "fixtures" / "wang2022" / "iss_i.json"


@pytest.fixture
def iss_i_config() -> FlowsheetConfig:
    """Load ISS-I config (full)."""
    config = load_flowsheet(FIXTURE)
    return config


@pytest.fixture
def iss_i_small_config() -> FlowsheetConfig:
    """Load ISS-I config with reduced stages for fast testing."""
    config = load_flowsheet(FIXTURE)
    for col in config.columns:
        col.n_stages = min(col.n_stages, 10)
        col.feed_positions = {
            k: max(2, min(col.n_stages - 1, int(v * col.n_stages / max(v, 1))))
            for k, v in col.feed_positions.items()
        }
    # Re-detect tear streams since column sizes changed
    from h2iso.flowsheet.schema import detect_tear_streams

    config.tear_streams = detect_tear_streams(config)
    return config


class TestIssITopology:
    def test_loads_without_error(self, iss_i_config):
        """ISS-I JSON loads and validates."""
        errors = validate_topology(iss_i_config)
        assert not errors, f"Validation errors: {errors}"

    def test_three_columns(self, iss_i_config):
        assert len(iss_i_config.columns) == 3
        names = {c.name for c in iss_i_config.columns}
        assert names == {"CD1", "CD2", "CD3"}

    def test_two_equilibrators(self, iss_i_config):
        assert len(iss_i_config.equilibrators) == 2
        names = {e.name for e in iss_i_config.equilibrators}
        assert names == {"E1", "E2"}

    def test_tear_streams_detected(self, iss_i_config):
        """Two recycle loops should produce at least 2 tear streams."""
        assert len(iss_i_config.tear_streams) >= 2

    def test_splitter_configured(self, iss_i_config):
        assert "CD2_bottom" in iss_i_config.splitter
        split = iss_i_config.splitter["CD2_bottom"]
        assert "E1" in split
        assert "E2" in split


class TestIssISmallSolve:
    """Solve with reduced stages for fast CI."""

    @pytest.fixture
    def small_result(self, iss_i_small_config):
        solver = SequentialModularSolver(
            iss_i_small_config,
            method="wegstein",
            continuation_substeps=0,
        )
        return solver.solve(max_iter=30, tol=1e-3)

    def test_converges(self, small_result):
        assert small_result.converged, (
            f"ISS-I did not converge: iterations={small_result.iterations}, "
            f"residual={small_result.tear_residual:.2e}"
        )

    def test_all_columns_in_results(self, small_result):
        for col_name in ("CD1", "CD2", "CD3"):
            assert col_name in small_result.column_results, (
                f"{col_name} missing from column_results"
            )

    def test_equilibrators_present_in_streams(self, small_result):
        """E1_out and E2_out should be in the stream bank."""
        assert "E1_out" in small_result.streams
        assert "E2_out" in small_result.streams

    def test_product_streams_exist(self, small_result):
        for key in (
            "CD1_distillate",
            "CD1_bottoms",
            "CD2_distillate",
            "CD2_bottoms",
            "CD3_distillate",
            "CD3_bottoms",
        ):
            assert key in small_result.streams, f"{key} missing"

    def test_temperatures_physical(self, small_result):
        """All temperatures in cryogenic range (14-35 K)."""
        for key, stream in small_result.streams.items():
            T = stream.temperature
            assert 14.0 <= T <= 35.0, f"{key}: T={T:.2f} K outside [14, 35]"

    def test_cd3_bottom_t2_enriched(self, small_result):
        """CD3 bottom should concentrate T2 (heaviest species)."""
        bot = small_result.streams["CD3_bottoms"]
        # T2 is index 5
        assert bot.composition[5] > 0.1, (
            f"CD3_bottom T2={bot.composition[5]:.4f}, expected > 0.1"
        )

    def test_cd1_top_h2_enriched(self, small_result):
        """CD1 top should concentrate H2 (lightest species)."""
        dist = small_result.streams["CD1_distillate"]
        # H2 is index 0
        assert dist.composition[0] > 0.1, (
            f"CD1_top H2={dist.composition[0]:.4f}, expected > 0.1"
        )

    def test_splitter_mass_conservation(self, iss_i_small_config):
        """After CD2, E1 flow + E2 flow ≈ CD2 bottom flow."""
        solver = SequentialModularSolver(
            iss_i_small_config,
            method="wegstein",
            continuation_substeps=0,
        )
        result = solver.solve(max_iter=30, tol=1e-3)
        if not result.converged:
            pytest.skip("Solve did not converge — cannot check splitter")

        cd2_bot = result.streams["CD2_bottoms"]
        e1_out = result.streams["E1_out"]
        e2_out = result.streams["E2_out"]
        total = e1_out.flow + e2_out.flow
        # With 50/50 split, total should be ≈ CD2_bottom (within Wegstein drift)
        assert total == pytest.approx(cd2_bot.flow, rel=0.10), (
            f"CD2_bot={cd2_bot.flow:.2f}, E1+E2={total:.2f}"
        )
