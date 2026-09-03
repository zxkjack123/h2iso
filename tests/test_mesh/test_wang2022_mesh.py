"""Wang 2022 MESH validation tests (Task 2.5).

Validates the h2iso MESH solver against Wang et al. 2022 Aspen Plus
results for the CFETR ISS-I CD2 column (75 stages).

Reference: Wang et al., Fusion Engineering and Design 177 (2022) 113078.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.mesh.column import ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver

FIXTURES = Path(__file__).parent.parent / "fixtures" / "wang2022"


@pytest.fixture
def wang2022_cd2_ref():
    """Load Wang 2022 ISS-I CD2 reference data."""
    with open(FIXTURES / "wang2022_issi_cd2.json") as f:
        return json.load(f)


@pytest.fixture
def cd2_75_result(wang2022_cd2_ref):
    """Solve CD2 75-stage column matching Wang 2022 specs."""
    ref = wang2022_cd2_ref

    feed = np.zeros(6)
    comp = ref["feed"]["composition_mole_fraction"]
    from h2iso.species import SPECIES_ORDER

    for i, sp in enumerate(SPECIES_ORDER):
        feed[i] = comp.get(sp, 0.0)

    col_data = ref["column"]
    base_spec = ColumnSpec(
        n_stages=15,
        feed_stage=8,
        feed_flow=ref["feed"]["total_flow_mol_h"],
        feed_composition=feed,
        pressure=col_data["pressure_top_Pa"],
        reflux_ratio=col_data["reflux_ratio"],
        distillate_to_feed=col_data["distillate_to_feed_ratio"],
    )

    # Use continuation to reach 75 stages
    solver = ContinuationSolver()
    solver.add_step("N", target=30, n_substeps=1)
    solver.add_step("N", target=col_data["total_stages"], n_substeps=3)
    cont_result = solver.solve(base_spec)

    assert cont_result.final.convergence_info["success"], (
        f"CD2 75-stage solve failed: {cont_result.final.convergence_info['status']}"
    )
    return cont_result.final


class TestWang2022CD2:
    """Validate CD2 column against Wang 2022 Aspen Plus results."""

    def test_convergence(self, cd2_75_result):
        """IPOPT should converge for CD2 75 stages."""
        assert cd2_75_result.convergence_info["success"]

    def test_top_d2_purity(self, cd2_75_result, wang2022_cd2_ref):
        """Top D2 purity should match Wang 2022 Table 9."""
        ref_d2 = wang2022_cd2_ref["expected_results"]["top_composition_mole_fraction"][
            "D2"
        ]
        calc_d2 = cd2_75_result.x_profile[0, 3]  # D2 index = 3

        # Accept within tolerance from fixture
        tol = wang2022_cd2_ref["tolerances"]["composition_rel"]
        rel_err = abs(calc_d2 - ref_d2) / ref_d2
        assert rel_err < tol, (
            f"Top D2: calc={calc_d2:.6f}, ref={ref_d2:.6f}, "
            f"rel_err={rel_err:.4f} > tol={tol}"
        )

    def test_top_dt_impurity(self, cd2_75_result, wang2022_cd2_ref):
        """Top DT impurity should be in correct order of magnitude."""
        ref_dt = wang2022_cd2_ref["expected_results"]["top_composition_mole_fraction"][
            "DT"
        ]
        calc_dt = cd2_75_result.x_profile[0, 4]  # DT index = 4

        # DT is very small, check order of magnitude (within factor 10 of reference)
        assert calc_dt < 10 * ref_dt, (
            f"DT impurity too high: {calc_dt:.6f} vs ref {ref_dt:.6f}"
        )
        # At least some DT is present
        assert calc_dt > 0, "DT should not be exactly zero"

    def test_bottom_composition(self, cd2_75_result, wang2022_cd2_ref):
        """Bottom composition should show DT enrichment."""
        ref_bot = wang2022_cd2_ref["expected_results"][
            "bottom_composition_mole_fraction"
        ]
        calc_x_bot = cd2_75_result.x_profile[-1]

        # DT should be enriched at bottom
        calc_dt_bot = calc_x_bot[4]  # DT index = 4
        ref_dt_bot = ref_bot["DT"]
        # Accept within tolerance
        tol = wang2022_cd2_ref["tolerances"]["composition_rel"]
        rel_err = abs(calc_dt_bot - ref_dt_bot) / max(ref_dt_bot, 1e-6)
        assert rel_err < tol, (
            f"Bot DT: calc={calc_dt_bot:.6f}, ref={ref_dt_bot:.6f}, "
            f"rel_err={rel_err:.4f}"
        )

    def test_temperature_top(self, cd2_75_result, wang2022_cd2_ref):
        """Top temperature should match Wang 2022 Table 8."""
        ref_T_top = wang2022_cd2_ref["expected_results"]["temperatures_K"]["top"]
        calc_T_top = cd2_75_result.T_profile[0]

        tol_K = wang2022_cd2_ref["tolerances"]["temperature_abs_K"]
        err = abs(calc_T_top - ref_T_top)
        assert err < tol_K, (
            f"T_top: calc={calc_T_top:.4f}K, ref={ref_T_top:.4f}K, "
            f"err={err:.4f}K > tol={tol_K}K"
        )

    def test_temperature_bottom(self, cd2_75_result, wang2022_cd2_ref):
        """Bottom temperature should match Wang 2022 Table 8."""
        ref_T_bot = wang2022_cd2_ref["expected_results"]["temperatures_K"]["bottom"]
        calc_T_bot = cd2_75_result.T_profile[-1]

        tol_K = wang2022_cd2_ref["tolerances"]["temperature_abs_K"]
        err = abs(calc_T_bot - ref_T_bot)
        assert err < tol_K, (
            f"T_bot: calc={calc_T_bot:.4f}K, ref={ref_T_bot:.4f}K, "
            f"err={err:.4f}K > tol={tol_K}K"
        )

    def test_temperature_monotone(self, cd2_75_result):
        """Temperature must increase from top to bottom."""
        T = cd2_75_result.T_profile
        for j in range(len(T) - 1):
            assert T[j + 1] >= T[j] - 0.01

    def test_mass_conservation(self, cd2_75_result, wang2022_cd2_ref):
        """Overall mass balance should be satisfied."""
        ref = wang2022_cd2_ref
        F = ref["feed"]["total_flow_mol_h"]
        D_F = ref["column"]["distillate_to_feed_ratio"]
        D = D_F * F
        B = F - D

        feed = np.zeros(6)
        comp = ref["feed"]["composition_mole_fraction"]
        from h2iso.species import SPECIES_ORDER

        for i, sp in enumerate(SPECIES_ORDER):
            feed[i] = comp.get(sp, 0.0)

        x_D = cd2_75_result.x_profile[0]
        x_B = cd2_75_result.x_profile[-1]

        for i in range(6):
            if feed[i] > 1e-10:
                balance = D * x_D[i] + B * x_B[i] - F * feed[i]
                rel_err = abs(balance) / (F * feed[i])
                assert rel_err < 1e-3, (
                    f"Component {i} mass balance error = {rel_err:.2e}"
                )

    def test_heat_load_order_of_magnitude(self, cd2_75_result, wang2022_cd2_ref):
        """Heat loads should be in correct order of magnitude."""
        ref_Q_cond = wang2022_cd2_ref["expected_results"]["heat_loads_W"]["condenser"]
        ref_Q_reb = wang2022_cd2_ref["expected_results"]["heat_loads_W"]["reboiler"]

        calc_Q_cond = cd2_75_result.condenser_duty
        calc_Q_reb = cd2_75_result.reboiler_duty

        tol = wang2022_cd2_ref["tolerances"]["heat_load_rel"]

        # Condenser should be negative (cooling)
        assert calc_Q_cond < 0, f"Condenser duty should be negative: {calc_Q_cond}"
        # Relative error within tolerance
        assert abs(calc_Q_cond - ref_Q_cond) / abs(ref_Q_cond) < tol

        # Reboiler should be positive (heating)
        assert calc_Q_reb > 0, f"Reboiler duty should be positive: {calc_Q_reb}"

        # Check relative deviation for reboiler
        if abs(ref_Q_reb) > 0:
            rel_err = abs(calc_Q_reb - ref_Q_reb) / abs(ref_Q_reb)
            assert rel_err < tol, (
                f"Q_reb: calc={calc_Q_reb:.1f}W, ref={ref_Q_reb:.1f}W, "
                f"rel_err={rel_err:.2f} > tol={tol}"
            )


class TestGoNoGo:
    """Go/No-Go determination."""

    def test_go_determination(self, cd2_75_result, wang2022_cd2_ref):
        """Document Go/No-Go status based on CD2 validation."""
        ref_d2 = wang2022_cd2_ref["expected_results"]["top_composition_mole_fraction"][
            "D2"
        ]
        calc_d2 = cd2_75_result.x_profile[0, 3]

        ref_T_top = wang2022_cd2_ref["expected_results"]["temperatures_K"]["top"]
        calc_T_top = cd2_75_result.T_profile[0]

        # Go criteria:
        # 1. D2 purity within 15% relative of reference
        d2_ok = abs(calc_d2 - ref_d2) / ref_d2 < 0.15
        # 2. Temperature within 1K
        T_ok = abs(calc_T_top - ref_T_top) < 1.0
        # 3. Solver converged
        conv_ok = cd2_75_result.convergence_info["success"]

        go = d2_ok and T_ok and conv_ok
        assert go, (
            f"Go/No-Go: FAIL — d2_ok={d2_ok} (calc={calc_d2:.6f}), "
            f"T_ok={T_ok} (calc={calc_T_top:.4f}K), conv_ok={conv_ok}"
        )
