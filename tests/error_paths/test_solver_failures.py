"""Error path coverage: solver and unit operation failures (T6.2)."""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.equilibrator.exchange import equilibrium_composition, keq
from h2iso.flowsheet.schema import FlowsheetConfig
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.flowsheet.unit import (
    ColumnUnit,
    PressureChangerUnit,
    SplitterUnit,
)
from h2iso.species import N_SPECIES
from h2iso.vle.eos import SRKQuantum


@pytest.fixture
def uniform_stream():
    from h2iso.flowsheet.stream import Stream

    return Stream(
        flow=10.0,
        composition=np.full(N_SPECIES, 1.0 / N_SPECIES),
        temperature=25.0,
        pressure=1.0e5,
        phase="vapor",
    )


def _empty_config() -> FlowsheetConfig:
    return FlowsheetConfig(
        feeds=[], columns=[], equilibrators=[], connections=[], products={}
    )


def test_solver_invalid_method():
    cfg = _empty_config()
    with pytest.raises(ValueError, match="method must be"):
        SequentialModularSolver(cfg, method="WEGSTEIN")
    with pytest.raises(ValueError, match="method must be"):
        SequentialModularSolver(cfg, method="nonsense")


def test_solver_invalid_on_unit_failure():
    cfg = _empty_config()
    with pytest.raises(ValueError, match="on_unit_failure"):
        SequentialModularSolver(cfg, on_unit_failure="bogus")


def test_column_unit_no_inputs():
    col = ColumnUnit(
        name="C1",
        n_stages=10,
        reflux_ratio=1.5,
        distillate_to_feed=0.5,
        pressure=1.0e5,
    )
    with pytest.raises(ValueError, match="no input streams"):
        col.solve({})


def test_splitter_unit_wrong_input_count(uniform_stream):
    sp = SplitterUnit(name="S1", ratios={"a": 0.5, "b": 0.5})
    with pytest.raises(ValueError, match="expects 1 input"):
        sp.solve({"in1": uniform_stream, "in2": uniform_stream})


def test_splitter_unit_no_ratios(uniform_stream):
    sp = SplitterUnit(name="S1")
    with pytest.raises(ValueError, match="ratios must be set"):
        sp.solve({"feed": uniform_stream})


def test_pressure_changer_invalid_mode():
    with pytest.raises(ValueError, match="mode must be one of"):
        PressureChangerUnit(name="P1", target_pressure=1.0e5, mode="explode")


def test_pressure_changer_invalid_target_pressure():
    with pytest.raises(ValueError, match="target_pressure must be > 0"):
        PressureChangerUnit(name="P1", target_pressure=-1.0, mode="throttle")


def test_pressure_changer_invalid_gamma():
    with pytest.raises(ValueError, match="gamma must be > 1"):
        PressureChangerUnit(
            name="P1", target_pressure=1.0e5, mode="compressor", gamma=0.9
        )


def test_pressure_changer_wrong_input_count(uniform_stream):
    pc = PressureChangerUnit(name="P1", target_pressure=2.0e5, mode="throttle")
    with pytest.raises(ValueError, match="expects 1 input"):
        pc.solve({"a": uniform_stream, "b": uniform_stream})


def test_keq_unknown_reaction():
    with pytest.raises(ValueError, match="Unknown reaction"):
        keq(25.0, "nonsense_reaction")


def test_equilibrium_composition_bad_atom_sum():
    with pytest.raises(ValueError, match="Atom fractions must sum to 1"):
        equilibrium_composition(alpha_H=0.1, alpha_D=0.1, alpha_T=0.1, T=25.0)


def test_srk_ln_phi_invalid_phase():
    srk = SRKQuantum()
    x = np.full(N_SPECIES, 1.0 / N_SPECIES)
    with pytest.raises(ValueError, match="phase must be 'L' or 'V'"):
        srk._ln_phi(25.0, 1.0e5, x, "vapour")


def test_continuation_unknown_param():
    from h2iso.mesh.continuation import ContinuationSolver

    solver = ContinuationSolver()
    solver.add_step("UNKNOWN_PARAM", target=10.0, n_substeps=1)
    # The error surfaces when solver actually processes the step; construct
    # a minimal ColumnSpec and trigger.
    from h2iso.mesh.column import ColumnSpec

    spec = ColumnSpec(
        n_stages=10,
        feed_stage=5,
        feed_flow=10.0,
        feed_composition=np.full(N_SPECIES, 1.0 / N_SPECIES),
        pressure=1.0e5,
        reflux_ratio=1.5,
        distillate_to_feed=0.5,
    )
    with pytest.raises(ValueError, match="Unknown continuation parameter"):
        solver.solve(spec)
