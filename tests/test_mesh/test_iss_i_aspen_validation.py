"""Validation test: h2iso vs Aspen Plus ISS-I 5-case baseline (张世坤 2026-05).

Loads the Aspen Plus baseline CSV (via JSON fixture) and verifies:
1. Feed composition matches statistical equilibrium (H/D/T atom → 6 species)
2. Mass balance consistency (input H/D/T = output H/D/T within Aspen tolerance)
3. Directional agreement: h2iso CD2 column gives similar product composition trends
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from h2iso.mesh.column import ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "wang2022" / "iss_i_aspen_baseline.json"
)

# Atomic masses
_M_H = 1.008
_M_D = 2.014
_M_T = 3.016


def _atom_to_species_equilibrium(H_g, D_g, T_g):
    """Convert H/D/T mass flows (g/h) to 6-species mole fractions under
    statistical equilibrium (random pairing)."""
    n_H = H_g / _M_H
    n_D = D_g / _M_D
    n_T = T_g / _M_T
    n_total = n_H + n_D + n_T
    if n_total <= 0:
        return np.zeros(6), 0.0

    x_H = n_H / n_total
    x_D = n_D / n_total
    x_T = n_T / n_total

    z = np.array(
        [
            x_H**2,  # H2
            2 * x_H * x_D,  # HD
            x_D**2,  # D2
            2 * x_H * x_T,  # HT
            2 * x_D * x_T,  # DT
            x_T**2,  # T2
        ]
    )
    F_total = n_total / 2.0  # each molecule has 2 atoms
    return z, F_total


def _species_flow_to_atom_flow(flow_mol_h, composition):
    """Convert species molar flow (mol/h) + 6-comp fraction to H/D/T mass
    flows (g/h) using the same formula as the Aspen task spec."""
    Q = flow_mol_h * np.asarray(composition)
    # Q: [H2, HD, D2, HT, DT, T2]
    H = (2 * Q[0] + Q[1] + Q[3]) * _M_H
    D = (Q[1] + 2 * Q[2] + Q[4]) * _M_D
    T = (Q[3] + Q[4] + 2 * Q[5]) * _M_T
    return H, D, T


@pytest.fixture(scope="module")
def baseline():
    with open(FIXTURE) as f:
        return json.load(f)


class TestAtomToSpeciesConversion:
    """Verify that the statistical equilibrium formula in the Aspen task
    spec (§3) is correctly implemented."""

    def test_tc1_conversion(self, baseline):
        tc = baseline["test_cases"][0]
        assert tc["case_id"] == "TC1"

        Hv = tc["feed_atom_flow_g_h"]["H"]
        Dv = tc["feed_atom_flow_g_h"]["D"]
        Tv = tc["feed_atom_flow_g_h"]["T"]

        z, F = _atom_to_species_equilibrium(Hv, Dv, Tv)

        ref = tc["feed_composition"]
        for i, sp in enumerate(["H2", "HD", "D2", "HT", "DT", "T2"]):
            assert z[i] == pytest.approx(ref[sp], rel=1e-3), (
                f"TC1 {sp}: calculated {z[i]:.6f}, expected {ref[sp]:.6f}"
            )

        assert F == pytest.approx(tc["feed_total_mol_h"], rel=1e-3)

    def test_all_cases_match(self, baseline):
        for tc in baseline["test_cases"]:
            Hv = tc["feed_atom_flow_g_h"]["H"]
            Dv = tc["feed_atom_flow_g_h"]["D"]
            Tv = tc["feed_atom_flow_g_h"]["T"]
            z, F = _atom_to_species_equilibrium(Hv, Dv, Tv)

            ref_z = tc["feed_composition"]
            for i, sp in enumerate(["H2", "HD", "D2", "HT", "DT", "T2"]):
                assert z[i] == pytest.approx(ref_z[sp], rel=1e-3), (
                    f"{tc['case_id']} {sp}: calc={z[i]:.6f}, ref={ref_z[sp]:.6f}"
                )
            assert abs(z.sum() - 1.0) < 1e-10
            assert F == pytest.approx(tc["feed_total_mol_h"], rel=1e-3)


class TestMassBalance:
    """Verify that the Aspen results satisfy mass conservation."""

    def test_mass_balance_all_cases(self, baseline):
        for tc in baseline["test_cases"]:
            H_in = tc["feed_atom_flow_g_h"]["H"]
            D_in = tc["feed_atom_flow_g_h"]["D"]
            T_in = tc["feed_atom_flow_g_h"]["T"]

            prods = tc["products_atom_flow_g_h"]
            H_out = sum(prods[k]["H"] for k in prods)
            D_out = sum(prods[k]["D"] for k in prods)
            T_out = sum(prods[k]["T"] for k in prods)

            # Relative error should be tiny (Aspen converged)
            for label, v_in, v_out in [
                ("H", H_in, H_out),
                ("D", D_in, D_out),
                ("T", T_in, T_out),
            ]:
                if v_in > 0:
                    err = abs(v_out - v_in) / v_in
                    assert err < 0.01, (
                        f"{tc['case_id']} {label}: in={v_in:.3f}, out={v_out:.3f}, err={err:.2e}"
                    )

    def test_mass_balance_matches_csv(self, baseline):
        for tc in baseline["test_cases"]:
            H_in = tc["feed_atom_flow_g_h"]["H"]
            D_in = tc["feed_atom_flow_g_h"]["D"]
            T_in = tc["feed_atom_flow_g_h"]["T"]
            total_in = H_in + D_in + T_in

            prods = tc["products_atom_flow_g_h"]
            total_out = sum(
                prods[k]["H"] + prods[k]["D"] + prods[k]["T"] for k in prods
            )

            calc_err = abs(total_out - total_in) / total_in if total_in > 0 else 0
            csv_err = tc["mass_balance_rel_err"]
            # Both the independent calculation and the CSV-reported error should
            # be very small (the CSV digitisation may introduce slight rounding).
            assert calc_err < 1e-3, f"{tc['case_id']}: calc={calc_err:.3e}"
            assert csv_err < 1e-3, f"{tc['case_id']}: csv={csv_err:.3e}"


class TestProductCompositions:
    """Verify product stream mole fractions are physically reasonable."""

    def test_cd3_bottom_T2_enrichment(self, baseline):
        """In ISS-I, CD3 bottom should concentrate T2."""
        for tc in baseline["test_cases"]:
            sds_t2 = tc["products_atom_flow_g_h"]["SDST2"]
            # T should dominate in SDST2 (CD3 bottom product)
            if sds_t2["H"] + sds_t2["D"] + sds_t2["T"] > 0:
                t_frac = sds_t2["T"] / (sds_t2["H"] + sds_t2["D"] + sds_t2["T"])
                assert t_frac > 0.5, f"{tc['case_id']} SDST2 T fraction: {t_frac:.3f}"

    def test_wds_low_T(self, baseline):
        """WDS (CD1 top + CD2 top) should be nearly T-free."""
        for tc in baseline["test_cases"]:
            wds = tc["products_atom_flow_g_h"]["WDS"]
            total = wds["H"] + wds["D"] + wds["T"]
            if total > 0:
                t_frac = wds["T"] / total
                assert t_frac < 0.1, (
                    f"{tc['case_id']} WDS T fraction: {t_frac:.3e} — should be near zero"
                )


class TestH2isoCD2Directional:
    """Compare h2iso CD2 column against Aspen trends (not absolute values).

    h2iso uses Souers vapor pressure + quantum corrections vs Aspen
    Peng-Robinson, so systematic offsets are expected. These tests
    verify *directional* agreement (light/heavy separation).
    """

    @pytest.fixture
    def cd2_solved(self, baseline):
        """Solve CD2 (100 stages) with TC1 feed using h2iso."""
        tc = baseline["test_cases"][0]
        z = np.array(
            [tc["feed_composition"][sp] for sp in ["H2", "HD", "D2", "HT", "DT", "T2"]]
        )

        base = ColumnSpec(
            n_stages=15,
            feed_stage=8,
            feed_flow=tc["feed_total_mol_h"],
            feed_composition=z,
            pressure=95000.0,  # mid-point of 90-100 kPa
            reflux_ratio=60,
            distillate_to_feed=0.78,
        )

        solver = ContinuationSolver()
        solver.add_step("N", target=30, n_substeps=1)
        solver.add_step("N", target=100, n_substeps=5)
        cont = solver.solve(base)
        assert cont.final.convergence_info["success"]
        return cont.final

    def test_heavy_enrichment_in_bottoms(self, cd2_solved):
        """Heavier species (DT, T2) should concentrate in bottoms."""
        x_top = cd2_solved.x_profile[0]
        x_bot = cd2_solved.x_profile[-1]

        # DT (index 4) + T2 (index 5) should be higher in bottom
        assert x_bot[4] + x_bot[5] > x_top[4] + x_top[5], (
            "Heavy species not enriched in bottoms"
        )

    def test_light_enrichment_in_top(self, cd2_solved):
        """Lighter species (H2, HD) should concentrate in distillate."""
        x_top = cd2_solved.x_profile[0]
        x_bot = cd2_solved.x_profile[-1]

        assert x_top[0] + x_top[1] > x_bot[0] + x_bot[1], (
            "Light species not enriched in distillate"
        )

    def test_temperature_profile_increases(self, cd2_solved):
        """T should increase monotonically from top to bottom."""
        T = cd2_solved.T_profile
        assert np.all(np.diff(T) > 0), f"T profile not monotonic: {T}"
