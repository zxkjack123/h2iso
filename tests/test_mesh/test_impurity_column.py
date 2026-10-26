"""Column-level impurity tests (impurity extension, second increment).

Runs the CD2 impurity fixture end-to-end:

1. the 6-species column solve is unchanged (baseline purity reproduced);
2. the impurity disposition layer classifies He-4 -> top, CO/N2 -> frozen
   (with warnings) over the *solved* CD2 temperature window;
3. top-product dilution by the non-condensable matches the exact
   flow-weighted value and stays within the declared demonstration 0.5% band for the
   0.5% He-4 feed of this fixture;
4. the corrected acceptance semantics are locked in as assertions (the
   original "99% to the top vent" claim holds only for helium -- see the
   impurity disposition documentation sec. 3.3).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.impurities import (
    classify_species,
    column_impurity_disposition,
    dilute_top_product,
)
from h2iso.mesh.column import ColumnSpec
from h2iso.mesh.continuation import ContinuationSolver

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "wang2022"
    / "wang2022_issi_cd2_impurity.json"
)


@pytest.fixture(scope="module")
def fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def cd2_result(fixture):
    """Solve the 6-species CD2 core with the hydrogen-isotope sub-mixture."""
    feed = fixture["feed"]
    z = np.array(
        [
            feed["composition_mole_fraction"][sp]
            for sp in ["H2", "HD", "HT", "D2", "DT", "T2"]
        ]
    )
    spec = ColumnSpec(
        n_stages=15,
        feed_stage=8,
        feed_flow=feed["total_flow_mol_h"],
        feed_composition=z,
        pressure=95_000.0,
        reflux_ratio=fixture["column"]["reflux_ratio"],
        distillate_to_feed=fixture["column"]["distillate_to_feed_ratio"],
    )
    solver = ContinuationSolver()
    solver.add_step("N", target=30, n_substeps=1)
    solver.add_step("N", target=75, n_substeps=3)
    cont = solver.solve(spec)
    assert cont.final.convergence_info["success"]
    return cont.final


class TestFixtureAndClassification:
    def test_fixture_keys(self, fixture):
        assert fixture["feed"]["impurities"] == {"CO": 0.01, "N2": 0.005, "He4": 0.005}
        assert "acceptance_semantics" in fixture

    def test_classification_over_cd2_window(self, cd2_result):
        t_min = float(cd2_result.T_profile[0])
        t_max = float(cd2_result.T_profile[-1])
        assert classify_species("He4", t_min, t_max)[0] == "to_top"
        assert classify_species("CO", t_min, t_max)[0] == "frozen_out"
        assert classify_species("N2", t_min, t_max)[0] == "frozen_out"

    def test_baseline_solve_matches_wang_purity(self, cd2_result):
        # the impurity layer must not perturb the 6-species core
        assert cd2_result.x_profile[0, 3] > 0.999  # D2 top purity


class TestDisposition:
    def _run(self, fixture, cd2_result, **kw):
        t_min = float(cd2_result.T_profile[0])
        t_max = float(cd2_result.T_profile[-1])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            disp = column_impurity_disposition(
                fixture["feed"]["impurities"],
                fixture["feed"]["total_flow_mol_h"],
                t_min,
                t_max,
                liquid_flow_mol_h=fixture["feed"]["total_flow_mol_h"]
                * (1 - fixture["column"]["distillate_to_feed_ratio"]),
                **kw,
            )
        return {d.species: d for d in disp}, caught

    def test_he_leaves_via_top(self, fixture, cd2_result):
        disp, _ = self._run(fixture, cd2_result)
        he = disp["He4"]
        assert he.status == "to_top"
        assert he.to_top_mol_h == pytest.approx(0.005 * 80.357, rel=1e-12)
        assert he.frozen_mol_h == 0.0
        assert he.dissolved_mol_h == 0.0

    def test_co_and_n2_frozen_with_warnings(self, fixture, cd2_result):
        disp, caught = self._run(fixture, cd2_result)
        assert disp["CO"].status == "frozen_out"
        assert disp["N2"].status == "frozen_out"
        # both frozen-out species must raise a visible warning
        msgs = " ".join(str(w.message) for w in caught)
        assert "CO" in msgs and "N2" in msgs and "FREEZE OUT" in msgs

    def test_n2_dissolved_trace_respects_cap(self, fixture, cd2_result):
        disp, _ = self._run(fixture, cd2_result)
        liquid_flow = 80.357 * (1 - 0.979)
        cap = 0.3e-6 * liquid_flow
        n2 = disp["N2"]
        # frozen species never reach the top; the dissolved trace travels
        # with the LIQUID (bottom product)
        assert n2.to_top_mol_h == 0.0
        assert n2.dissolved_mol_h == pytest.approx(cap, rel=1e-6)
        assert n2.frozen_mol_h == pytest.approx(0.005 * 80.357 - cap, rel=1e-6)

    def test_solubility_override(self, fixture, cd2_result):
        disp, _ = self._run(fixture, cd2_result, solubility_ppm={"CO": 2.0})
        liquid_flow = 80.357 * (1 - 0.979)
        co = disp["CO"]
        assert co.to_top_mol_h == 0.0
        assert co.dissolved_mol_h == pytest.approx(2.0e-6 * liquid_flow, rel=1e-6)
        assert co.frozen_mol_h == pytest.approx(
            0.01 * 80.357 - 2.0e-6 * liquid_flow, rel=1e-6
        )

    def test_disposition_dict_roundtrip(self, fixture, cd2_result):
        disp, _ = self._run(fixture, cd2_result)
        d = disp["He4"].to_dict()
        assert d["species"] == "He4" and d["status"] == "to_top"


class TestTopProductDilution:
    def test_exact_dilution_and_acceptance_band(self, fixture, cd2_result):
        t_min = float(cd2_result.T_profile[0])
        t_max = float(cd2_result.T_profile[-1])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            disp = column_impurity_disposition(
                fixture["feed"]["impurities"],
                80.357,
                t_min,
                t_max,
                liquid_flow_mol_h=80.357 * (1 - 0.979),
            )
        to_top = {
            d.species: d.to_top_mol_h
            for d in disp
            if d.status == "to_top" and d.to_top_mol_h > 0
        }
        d_flow = 0.979 * 80.357
        x_dil, rel = dilute_top_product(
            {
                "D2": float(cd2_result.x_profile[0, 3]),
                "DT": float(cd2_result.x_profile[0, 4]),
            },
            to_top,
            d_flow,
        )
        he_flow = to_top["He4"]
        assert x_dil["He4"] == pytest.approx(he_flow / (d_flow + he_flow), rel=1e-12)
        # corrected acceptance: dilution <= He feed fraction (0.5 %) band
        assert rel < 0.006
        assert rel > 0.004

    def test_errors(self):
        with pytest.raises(ValueError, match="must be > 0"):
            dilute_top_product({"D2": 1.0}, {"He4": 1.0}, 0.0)
        with pytest.raises(KeyError, match="not an impurity"):
            column_impurity_disposition({"Ar": 0.01}, 10.0, 23.0, 24.0)
        with pytest.raises(ValueError, match="invalid temperature window"):
            classify_species("He4", 30.0, 19.0)


class TestFixtureProvenance:
    """Cross-system mismatch guard for this fixture's provenance.

    The tree carries more than one cascade-parameter system, so fixtures
    aligned by name alone can be mis-attributed silently. The anchors below
    are fixed literals plus a cross-check against the independent same-system
    reference fixture in this directory; neither is read back from the fixture
    under test, so an edit that points this fixture at another system cannot
    pass.

    This fixture is an experimental demonstration artefact. Its impurity basis
    is declared as an experimental basis and its acceptance semantics are stated in
    corrected form; it is not Aspen output and must not be mixed with the Aspen
    validation baseline.
    """

    REFERENCE = (
        Path(__file__).parent.parent
        / "fixtures"
        / "wang2022"
        / "wang2022_issi_cd2.json"
    )
    ASPEN_BASELINE = (
        Path(__file__).parent.parent
        / "fixtures"
        / "wang2022"
        / "iss_i_aspen_baseline.json"
    )

    @staticmethod
    def _load(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_source_names_its_own_system(self, fixture):
        src = fixture["source"]
        # fixed anchors -- the source system this fixture claims to extend
        assert src["doi"] == "10.1016/j.fusengdes.2022.113078"
        assert src["journal"] == "Fusion Engineering and Design"
        assert src["volume"] == 177
        assert src["year"] == 2022
        assert "ISS-I" in src["model"]  # ISS-I, the inner fuel cycle
        assert "CD2" in src["model"]  # the CD2 column, not another column
        # independent cross-check: the same-system reference agrees
        ref = self._load(self.REFERENCE)["source"]
        assert src["doi"] == ref["doi"]
        assert src["volume"] == ref["volume"]
        assert src["journal"] == ref["journal"]

    def test_operating_point_matches_the_reference_system(self, fixture):
        ref = self._load(self.REFERENCE)
        assert fixture["feed"]["total_flow_mol_h"] == ref["feed"]["total_flow_mol_h"]
        for key in (
            "total_stages",
            "feed_stage",
            "reflux_ratio",
            "distillate_to_feed_ratio",
            "pressure_top_Pa",
            "pressure_bottom_Pa",
            "inside_diameter_m",
            "HETP_m",
        ):
            assert fixture["column"][key] == ref["column"][key], key

    def test_impurity_basis_is_an_extension_not_aspen(self, fixture):
        # fixed anchor: the impurity basis as numeric literals
        assert fixture["feed"]["impurities"] == {
            "CO": 0.01,
            "N2": 0.005,
            "He4": 0.005,
        }
        extension = fixture["source"]["impurity_extension"]
        # the free text must restate the same basis as the numeric anchor
        # above (percentages derived from it, not re-typed) ...
        basis = fixture["feed"]["impurities"]
        assert "He-4" in extension
        assert f"{basis['CO']:.0%} CO" in extension
        assert f"{basis['N2']:.1%} N2" in extension
        # ... and its destination claim must agree with the recorded
        # behaviour for the non-condensable species ...
        lowered = extension.lower()
        assert ("top-vent" in lowered) == (
            fixture["expected_impurity_behaviour"]["He4"]["status"] == "to_top"
        )
        # ... and the helium fraction quoted in the text must equal the same
        # numeric basis as well
        assert f"{basis['He4']:.1%} He-4" in extension
        # this artefact is separate from the Aspen-derived material: the
        # same-system reference carries no impurity basis at all,
        assert "impurities" not in self._load(self.REFERENCE)["feed"]
        # ...and neither does the Aspen validation baseline, so the two must
        # never be mixed or quoted as one another
        baseline = self._load(self.ASPEN_BASELINE)
        assert "impurities" not in json.dumps(baseline)
        # the acceptance semantics are recorded in corrected form, alongside
        # the original claim they replace
        semantics = fixture["acceptance_semantics"]
        assert "99%" in semantics["original_claim"]
        assert "only for the helium" in semantics["corrected"]
