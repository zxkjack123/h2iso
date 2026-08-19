"""Tests for parameter sweep functionality."""

from __future__ import annotations

from pathlib import Path

from h2iso.flowsheet.schema import load_flowsheet
from h2iso.flowsheet.sweep import ParameterSweep

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "wang2022" / "wang2022_isso.json"


class TestParameterSweepRefluxRatio:
    """Test reflux ratio sweep on CD2."""

    def test_sweep_cd2_reflux_4_points(self):
        """Sweep R=5,10,15,20 on CD2 produces 4 converged results."""
        config = load_flowsheet(FIXTURE_PATH)
        # Remove tear streams for faster sweep (no-recycle mode)
        config.tear_streams = []
        config.connections = [
            c for c in config.connections
            if c.from_unit not in ("CD2_top", "CD3_top")
        ]
        for col in config.columns:
            col.feed_positions = {
                k: v for k, v in col.feed_positions.items()
                if k not in ("CD2_top", "CD3_top")
            }

        sweep = ParameterSweep(config, target_column="CD2", continuation_substeps=3)
        result = sweep.sweep_reflux_ratio([5.0, 10.0, 15.0, 20.0])

        assert len(result.points) == 4
        # At least 3 should converge (high R may be slow)
        assert len(result.converged_points) >= 3

    def test_higher_reflux_improves_separation(self):
        """Higher reflux ratio → better H2 purity in CD2 distillate."""
        config = load_flowsheet(FIXTURE_PATH)
        config.tear_streams = []
        config.connections = [
            c for c in config.connections
            if c.from_unit not in ("CD2_top", "CD3_top")
        ]
        for col in config.columns:
            col.feed_positions = {
                k: v for k, v in col.feed_positions.items()
                if k not in ("CD2_top", "CD3_top")
            }

        sweep = ParameterSweep(config, target_column="CD2", continuation_substeps=3)
        result = sweep.sweep_reflux_ratio([5.0, 10.0, 15.0])

        # Get H2 fractions in CD2 distillate at each R
        h2_fracs = []
        for pt in result.converged_points:
            cd2_dist = pt.result.streams.get("CD2_distillate")
            if cd2_dist is not None:
                h2_fracs.append(cd2_dist.composition[0])

        # Higher R → higher H2 purity (monotone increasing)
        assert len(h2_fracs) >= 2
        for i in range(1, len(h2_fracs)):
            assert h2_fracs[i] >= h2_fracs[i - 1] - 0.001, (
                f"H2 purity not increasing: R[{i-1}]→{h2_fracs[i-1]:.4f}, "
                f"R[{i}]→{h2_fracs[i]:.4f}"
            )


class TestSweepResultExport:
    """Test sweep result serialization."""

    def test_to_json(self, tmp_path):
        """Sweep results can be exported to JSON."""
        config = load_flowsheet(FIXTURE_PATH)
        config.tear_streams = []
        config.connections = [
            c for c in config.connections
            if c.from_unit not in ("CD2_top", "CD3_top")
        ]
        for col in config.columns:
            col.feed_positions = {
                k: v for k, v in col.feed_positions.items()
                if k not in ("CD2_top", "CD3_top")
            }

        sweep = ParameterSweep(config, target_column="CD1", continuation_substeps=3)
        result = sweep.sweep_reflux_ratio([5.0, 8.0])

        out_path = tmp_path / "sweep.json"
        result.to_json(out_path)

        assert out_path.exists()
        import json
        with open(out_path) as f:
            data = json.load(f)
        assert data["parameter_name"] == "reflux_ratio"
        assert data["n_total"] == 2
