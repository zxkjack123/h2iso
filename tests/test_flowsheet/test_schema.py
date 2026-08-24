"""Tests for Flowsheet JSON Schema loading and topology analysis (Task 2.1.2)."""

from pathlib import Path

import numpy as np
import pytest

from h2iso.flowsheet.schema import (
    Connection,
    FlowsheetConfig,
    detect_tear_streams,
    load_flowsheet,
    validate_topology,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "wang2022"


class TestLoadFlowsheet:
    """Test load_flowsheet() with wang2022_isso.json."""

    def test_loads_successfully(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        assert isinstance(config, FlowsheetConfig)

    def test_feeds_parsed(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        assert len(config.feeds) == 2
        feed_names = {f.name for f in config.feeds}
        assert "WDS" in feed_names
        assert "TES" in feed_names

    def test_feed_composition(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        wds = next(f for f in config.feeds if f.name == "WDS")
        assert wds.flow == pytest.approx(280.0)
        assert wds.composition[0] > 0.99  # H2 dominant
        np.testing.assert_allclose(wds.composition.sum(), 1.0, atol=1e-6)

    def test_columns_parsed(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        assert len(config.columns) == 3
        col_names = {c.name for c in config.columns}
        assert col_names == {"CD1", "CD2", "CD3"}

    def test_column_specs(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        cd1 = next(c for c in config.columns if c.name == "CD1")
        assert cd1.n_stages == 60
        assert cd1.reflux_ratio == 6
        assert cd1.distillate_to_feed == pytest.approx(0.9948)

    def test_equilibrators_detected(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        assert len(config.equilibrators) >= 1
        eq_names = {e.name for e in config.equilibrators}
        assert "equilibrator" in eq_names

    def test_connections_parsed(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        assert len(config.connections) >= 6

    def test_products_parsed(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        assert "CD1_top" in config.products
        assert "CD3_bottom" in config.products


class TestValidateTopology:
    """Test validate_topology()."""

    def test_valid_topology(self):
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        errors = validate_topology(config)
        assert errors == []

    def test_invalid_connection_detected(self):
        """A topology with unknown unit references should report errors."""
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        # Add a bad connection
        from h2iso.flowsheet.schema import Connection

        config.connections.append(
            Connection(
                from_unit="NONEXISTENT_UNIT",
                to_unit="ANOTHER_FAKE",
            )
        )
        errors = validate_topology(config)
        assert len(errors) > 0
        assert any("NONEXISTENT_UNIT" in e or "ANOTHER_FAKE" in e for e in errors)


class TestDetectTearStreams:
    """Test detect_tear_streams()."""

    def test_recycle_detected(self):
        """ISS-O has a recycle loop: CD2_bottom_recycle -> CD1."""
        config = load_flowsheet(FIXTURE_DIR / "wang2022_isso.json")
        tear_names = [t.name for t in config.tear_streams]
        # There should be at least one tear stream in the ISS-O topology
        assert len(config.tear_streams) >= 1
        # The recycle from CD2/CD3 back to CD1/CD2 should be detected
        has_recycle = any(
            "CD1" in t.to_unit or "CD2" in t.to_unit for t in config.tear_streams
        )
        assert has_recycle, f"No recycle detected. Tears: {tear_names}"

    def test_no_cycle_no_tear(self):
        """A linear topology should have no tear streams."""
        config = FlowsheetConfig(
            feeds=[],
            columns=[],
            equilibrators=[],
            connections=[
                Connection(from_unit="A", to_unit="B"),
                Connection(from_unit="B", to_unit="C"),
            ],
            products={},
        )
        tears = detect_tear_streams(config)
        assert tears == []
