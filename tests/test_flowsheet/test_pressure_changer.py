"""Tests for PressureChangerUnit (throttle, pump, compressor)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from h2iso.flowsheet.schema import PressureChangerConfig, load_flowsheet
from h2iso.flowsheet.stream import Stream
from h2iso.flowsheet.unit import PressureChangerUnit
from h2iso.species import N_SPECIES


def _uniform_stream(flow: float = 10.0, T: float = 25.0, P: float = 2.0e5) -> Stream:
    comp = np.ones(N_SPECIES) / N_SPECIES
    return Stream(flow=flow, composition=comp, temperature=T, pressure=P, phase="liquid")


class TestPressureChangerModeValidation:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be one of"):
            PressureChangerUnit(name="V1", target_pressure=1e5, mode="expander")

    def test_nonpositive_target_pressure_raises(self):
        with pytest.raises(ValueError, match="target_pressure"):
            PressureChangerUnit(name="V1", target_pressure=0.0, mode="throttle")

    def test_gamma_at_one_raises(self):
        with pytest.raises(ValueError, match="gamma"):
            PressureChangerUnit(name="C1", target_pressure=1e5, mode="compressor", gamma=1.0)


class TestThrottleIsenthalpic:
    """h2iso enthalpy has no explicit P-dependence → throttle preserves T.

    Acceptance criterion: ΔT sign consistent with JT coefficient. The h2iso
    model corresponds to an ideal-gas JT coefficient of zero, so ΔT == 0 is
    the only consistent answer.
    """

    def test_throttle_preserves_temperature(self):
        unit = PressureChangerUnit(name="V1", target_pressure=5.0e4, mode="throttle")
        src = _uniform_stream(T=25.0, P=2.0e5)
        out = unit.solve({"in": src})["out"]
        assert out.pressure == pytest.approx(5.0e4)
        assert out.temperature == pytest.approx(25.0)

    def test_throttle_preserves_flow_and_composition(self):
        unit = PressureChangerUnit(name="V1", target_pressure=8.0e4, mode="throttle")
        src = _uniform_stream(flow=12.5)
        out = unit.solve({"in": src})["out"]
        assert out.flow == pytest.approx(12.5)
        np.testing.assert_allclose(out.composition, src.composition)


class TestPump:
    def test_pump_raises_pressure_T_unchanged(self):
        unit = PressureChangerUnit(name="P1", target_pressure=5.0e5, mode="pump")
        src = _uniform_stream(T=24.0, P=1.0e5)
        out = unit.solve({"in": src})["out"]
        assert out.pressure == pytest.approx(5.0e5)
        assert out.temperature == pytest.approx(24.0)


class TestCompressor:
    def test_isentropic_temperature_rise(self):
        gamma = 1.4
        T_in, P_in, P_out = 30.0, 1.0e5, 4.0e5
        unit = PressureChangerUnit(
            name="C1", target_pressure=P_out, mode="compressor", gamma=gamma
        )
        src = _uniform_stream(T=T_in, P=P_in)
        out = unit.solve({"in": src})["out"]
        expected = T_in * (P_out / P_in) ** ((gamma - 1.0) / gamma)
        assert out.temperature == pytest.approx(expected, rel=1e-12)
        assert out.temperature > T_in
        assert out.pressure == pytest.approx(P_out)


class TestSchemaValidation:
    def test_pressure_changer_section_in_schema(self):
        schema_path = Path(__file__).parents[2] / "src/h2iso/data/schemas/flowsheet_v1.json"
        schema = json.loads(schema_path.read_text())
        props = schema["properties"]
        assert "pressure_changers" in props
        pc = props["pressure_changers"]
        assert pc["type"] == "object"
        inner = pc["additionalProperties"]
        assert set(inner["required"]) == {"target_pressure_Pa", "mode"}
        assert set(inner["properties"]["mode"]["enum"]) == {
            "throttle", "pump", "compressor"
        }
        assert inner["properties"]["target_pressure_Pa"]["exclusiveMinimum"] == 0

    def test_pressure_changer_mode_enum_complete(self):
        schema_path = Path(__file__).parents[2] / "src/h2iso/data/schemas/flowsheet_v1.json"
        schema = json.loads(schema_path.read_text())
        modes = schema["properties"]["pressure_changers"]["additionalProperties"][
            "properties"
        ]["mode"]["enum"]
        assert "expander" not in modes


class TestLoadFlowsheetWithPressureChanger:
    def test_load_parses_pressure_changers(self, tmp_path: Path):
        cfg = {
            "feeds": {
                "F1": {
                    "total_flow_mol_h": 10.0,
                    "composition_mole_fraction": {"H2": 1.0},
                    "target_column": "C1",
                    "feed_stage": 5,
                }
            },
            "columns": {
                "C1": {
                    "total_stages": 10,
                    "reflux_ratio": 5.0,
                    "distillate_to_feed_ratio": 0.5,
                }
            },
            "topology": {"connections": [{"from": "F1_feed", "to": "C1"}]},
            "pressure_changers": {
                "V1": {"target_pressure_Pa": 5.0e4, "mode": "throttle"},
                "C1k": {"target_pressure_Pa": 5.0e5, "mode": "compressor", "gamma": 1.3},
            },
        }
        cfg_path = tmp_path / "fs.json"
        cfg_path.write_text(json.dumps(cfg))
        loaded = load_flowsheet(cfg_path)
        assert len(loaded.pressure_changers) == 2
        names = {p.name for p in loaded.pressure_changers}
        assert names == {"V1", "C1k"}
        v1 = next(p for p in loaded.pressure_changers if p.name == "V1")
        assert v1.mode == "throttle"
        assert v1.target_pressure == pytest.approx(5.0e4)
        assert v1.gamma == pytest.approx(1.4)  # default
        c1k = next(p for p in loaded.pressure_changers if p.name == "C1k")
        assert isinstance(c1k, PressureChangerConfig)
        assert c1k.gamma == pytest.approx(1.3)
