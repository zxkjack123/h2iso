"""Tests for stage-efficiency models (holdup/efficiency extension).

Covers:
1. EfficiencySpec expansion (scalar / per-stage / per-stage-species / dict)
2. Scalar helper functions (Murphree y_out, realised efficiency, K_eff)
3. Solver integration: E = 1 is bitwise-identical to the ideal baseline
4. Solver integration: E < 1 reduces separation; reboiler stays equilibrium
5. Error paths (bad shapes, values, unsupported EOS combination)
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("casadi")  # h2iso.mesh imports the CasADi solver package

from h2iso.mesh.column import Column, ColumnSpec
from h2iso.mesh.efficiency import (
    EfficiencySpec,
    k_effective,
    murphree_efficiency,
    murphree_vapor_y_out,
)
from h2iso.species import SPECIES_ORDER
from h2iso.vle.souers import pvap

N_STAGES = 12
N_SPECIES = 6


def _d2_dt_feed() -> np.ndarray:
    z = np.zeros(N_SPECIES)
    z[3] = 0.98  # D2
    z[4] = 0.02  # DT
    return z


def _spec(efficiency: EfficiencySpec | None = None) -> ColumnSpec:
    return ColumnSpec(
        n_stages=N_STAGES,
        feed_stage=6,
        feed_flow=10.0,
        feed_composition=_d2_dt_feed(),
        pressure=95000.0,
        reflux_ratio=15.0,
        distillate_to_feed=0.9,
        efficiency=efficiency,
    )


class TestSpecExpansion:
    def test_scalar(self):
        mat = EfficiencySpec(value=0.8).to_matrix(N_STAGES, N_SPECIES)
        assert mat.shape == (N_STAGES, N_SPECIES)
        assert np.all(mat == 0.8)

    def test_none_is_ones(self):
        mat = EfficiencySpec(value=None).to_matrix(N_STAGES, N_SPECIES)
        assert np.all(mat == 1.0)

    def test_per_stage_array(self):
        arr = np.linspace(0.5, 1.0, N_STAGES)
        mat = EfficiencySpec(value=arr).to_matrix(N_STAGES, N_SPECIES)
        assert mat.shape == (N_STAGES, N_SPECIES)
        assert np.allclose(mat[:, 0], arr)
        assert np.allclose(mat[:, 0], mat[:, -1])

    def test_full_matrix(self):
        arr = np.full((N_STAGES, N_SPECIES), 0.9)
        arr[3, 2] = 0.5
        mat = EfficiencySpec(value=arr).to_matrix(N_STAGES, N_SPECIES)
        assert mat[3, 2] == 0.5

    def test_dict_one_indexed_stage(self):
        # stage 1 = condenser, species index 3 = D2
        mat = EfficiencySpec(value={(1, 3): 0.5, (N_STAGES, 0): 0.7}).to_matrix(
            N_STAGES, N_SPECIES
        )
        assert mat[0, 3] == 0.5
        assert mat[N_STAGES - 1, 0] == 0.7
        assert mat[1, 3] == 1.0

    def test_bad_shape_raises(self):
        with pytest.raises(ValueError, match="shape"):
            EfficiencySpec(value=np.ones((N_STAGES + 1, N_SPECIES))).to_matrix(
                N_STAGES, N_SPECIES
            )

    def test_bad_stage_index_raises(self):
        with pytest.raises(ValueError, match="stage"):
            EfficiencySpec(value={(0, 1): 0.9}).to_matrix(N_STAGES, N_SPECIES)
        with pytest.raises(ValueError, match="stage"):
            EfficiencySpec(value={(N_STAGES + 1, 1): 0.9}).to_matrix(
                N_STAGES, N_SPECIES
            )

    def test_bad_species_index_raises(self):
        with pytest.raises(ValueError, match="species"):
            EfficiencySpec(value={(1, N_SPECIES): 0.9}).to_matrix(N_STAGES, N_SPECIES)

    def test_zero_or_negative_raises(self):
        with pytest.raises(ValueError, match="> 0"):
            EfficiencySpec(value=0.0).to_matrix(N_STAGES, N_SPECIES)
        with pytest.raises(ValueError, match="> 0"):
            EfficiencySpec(value=-0.2).to_matrix(N_STAGES, N_SPECIES)

    def test_above_one_warns(self):
        with pytest.warns(UserWarning, match="overshoot"):
            mat = EfficiencySpec(value=1.2).to_matrix(N_STAGES, N_SPECIES)
        assert np.all(mat == 1.2)

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            EfficiencySpec(mode="bogus")  # type: ignore[arg-type]


class TestScalarHelpers:
    def test_murphree_y_out(self):
        assert murphree_vapor_y_out(0.1, 0.5, 0.8) == pytest.approx(0.42)
        assert murphree_vapor_y_out(0.1, 0.5, 1.0) == pytest.approx(0.5)

    def test_murphree_roundtrip(self):
        y_in, y_eq, E = 0.2, 0.7, 0.6
        y_out = murphree_vapor_y_out(y_in, y_eq, E)
        assert murphree_efficiency(y_in, y_out, y_eq) == pytest.approx(E)

    def test_murphree_efficiency_degenerate(self):
        # equilibrium already reached -> defined as 1.0
        assert murphree_efficiency(0.5, 0.5, 0.5) == pytest.approx(1.0)

    def test_k_effective(self):
        assert k_effective(2.0, 0.9) == pytest.approx(1.8)
        assert np.allclose(k_effective(np.array([1.0, 2.0]), 0.5), [0.5, 1.0])


class TestSolverIntegration:
    def test_efficiency_one_is_bitwise_baseline(self):
        """Murphree E=1 must reproduce the ideal-stage solver exactly."""
        r_ideal = Column(_spec()).solve()
        r_unit = Column(_spec(EfficiencySpec(mode="murphree", value=1.0))).solve()
        assert np.array_equal(r_ideal.x_profile, r_unit.x_profile)
        assert np.array_equal(r_ideal.y_profile, r_unit.y_profile)
        assert np.array_equal(r_ideal.T_profile, r_unit.T_profile)

    def test_murphree_reduces_separation(self):
        r_ideal = Column(_spec()).solve()
        r_eff = Column(_spec(EfficiencySpec(mode="murphree", value=0.8))).solve()
        # less efficient stages -> less enrichment of the heavy key at the
        # bottom, i.e. x_D2(bottom) is higher (closer to feed).
        assert r_eff.x_profile[-1, 3] > r_ideal.x_profile[-1, 3]
        # ... and the top is less pure in the light key
        assert r_eff.x_profile[0, 3] < r_ideal.x_profile[0, 3]

    def test_vaporization_reduces_separation(self):
        r_ideal = Column(_spec()).solve()
        r_eff = Column(_spec(EfficiencySpec(mode="vaporization", value=0.9))).solve()
        assert r_eff.x_profile[0, 3] < r_ideal.x_profile[0, 3]

    def test_result_records_applied_matrix(self):
        spec = _spec(EfficiencySpec(mode="murphree", value=0.85))
        result = Column(spec).solve()
        assert result.murphree_eff is not None
        assert result.murphree_eff.shape == (N_STAGES, N_SPECIES)
        assert np.all(result.murphree_eff == 0.85)

    def test_result_matrix_none_without_spec(self):
        assert Column(_spec()).solve().murphree_eff is None

    def test_reboiler_stays_equilibrium(self):
        """The reboiler (stage N) keeps y = K x even with a Murphree spec."""
        spec = _spec(EfficiencySpec(mode="murphree", value=0.5))
        result = Column(spec).solve()
        T_R = result.T_profile[-1]
        x_R = result.x_profile[-1]
        y_R = result.y_profile[-1]
        K = np.array([pvap(T_R, sp) / spec.pressure for sp in SPECIES_ORDER])
        assert np.allclose(y_R, K * x_R, atol=1e-8)

    def test_peng_robinson_with_efficiency_raises(self):
        spec = _spec(EfficiencySpec(mode="murphree", value=0.9))
        spec.eos = "peng-robinson"
        with pytest.raises(NotImplementedError, match="efficiency"):
            Column(spec).solve()
