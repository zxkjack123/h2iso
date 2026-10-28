"""Flowsheet-level impurity routing tests (flowsheet impurity tracer layer).

Two layers:

* pure unit tests on a synthetic two/three-column topology with a fake
  solved result -- no solver, no CasADi (the routing layer is a
  post-processing tracer and must not need the NLP stack);
* one integration test on the real ISS-I cascade (CasADi-guarded), which
  locks in the CFEDR answer: He injected at CD2 leaves through the CD2
  top product (WDS-D), CO/N2 deposit in CD2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from h2iso.flowsheet.schema import (
    ColumnConfig,
    Connection,
    EquilibratorConfig,
    FlowsheetConfig,
)
from h2iso.impurity_routing import route_impurities
from h2iso.purge import PurgeSpec

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "wang2022"


# ----------------------------------------------------------------------
# synthetic topology + fake solved result (no CasADi)
# ----------------------------------------------------------------------


class _FakeColumnResult:
    def __init__(self, t_top, t_bottom, l_bottom):
        n = 5
        self.T_profile = np.linspace(t_top, t_bottom, n)
        self.L_profile = np.linspace(l_bottom, l_bottom, n)
        # D2-rich top liquid, for the purge design (V1.2 tests)
        x = np.zeros(6)
        x[3] = 1.0
        self.x_profile = np.tile(x, (n, 1))


class _FakeFlowsheetResult:
    def __init__(self, windows, bottoms):
        self.column_results = {
            name: _FakeColumnResult(t0, t1, bottoms[name])
            for name, (t0, t1) in windows.items()
        }


def _column(name, stages=20):
    return ColumnConfig(
        name=name,
        n_stages=stages,
        reflux_ratio=10.0,
        distillate_to_feed=0.8,
        feed_positions={},
        pressure=95000.0,
    )


def _config(columns, connections, products, splitter=None, equilibrators=()):
    return FlowsheetConfig(
        feeds=[],
        columns=[_column(c) for c in columns],
        equilibrators=[EquilibratorConfig(name=e) for e in equilibrators],
        connections=[Connection(from_unit=a, to_unit=b) for a, b in connections],
        products={p: "" for p in products},
        splitter=splitter or {},
    )


ISS_WINDOW = (23.5, 24.9)  # CD2-like: freezes CO/N2, He non-condensable


class TestSyntheticRouting:
    def test_helium_vented_via_terminal_top(self):
        cfg = _config(
            ["A", "B"],
            [("A_top", "B")],
            products=["B_top"],
        )
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 5.0, "B": 5.0}
        )
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4}})
        assert len(rep.routes) == 1
        r = rep.routes[0]
        assert r.status == "vent"
        assert r.destination == "B_top"
        assert r.path == ["A", "A_top", "B", "B_top"]
        assert r.flow_mol_h == pytest.approx(0.4)

    def test_helium_vented_at_entry_column_when_unconnected(self):
        cfg = _config(["A"], [], products=["A_top"])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4}})
        assert rep.routes[0].destination == "A_top"
        assert rep.routes[0].status == "vent"

    def test_frozen_and_dissolved_split(self):
        cfg = _config(["A"], [], products=[])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 1000.0})
        rep = route_impurities(cfg, res, {"A": {"N2": 1.0e-3}})
        by_status = rep.by_status()
        # 0.3 ppm cap on 1000 mol/h liquid = 3e-4 mol/h dissolved
        assert by_status["dissolved"]["N2"] == pytest.approx(3.0e-4, rel=1e-9)
        assert by_status["frozen"]["N2"] == pytest.approx(1.0e-3 - 3.0e-4, rel=1e-9)
        assert rep.routes[1].destination == "A_bottom"
        assert rep.frozen_columns() == {"A": {"N2": pytest.approx(7.0e-4)}}

    def test_helium_multihop_chain(self):
        # CD3_top -> CD2 -> CD2_top -> CD1 -> CD1_top, the ISS-O pattern
        cfg = _config(
            ["CD1", "CD2", "CD3"],
            [("CD3_top", "CD2"), ("CD2_top", "CD1")],
            products=["CD1_top"],
        )
        res = _FakeFlowsheetResult(
            {"CD1": ISS_WINDOW, "CD2": ISS_WINDOW, "CD3": ISS_WINDOW},
            {"CD1": 1.0, "CD2": 1.0, "CD3": 1.0},
        )
        rep = route_impurities(cfg, res, {"CD3": {"He4": 0.1}})
        r = rep.routes[0]
        assert r.destination == "CD1_top"
        assert r.path == ["CD3", "CD3_top", "CD2", "CD2_top", "CD1", "CD1_top"]
        assert r.flow_mol_h == pytest.approx(0.1)

    def test_helium_passes_through_equilibrator(self):
        cfg = _config(
            ["A", "B"],
            [("A_top", "eq"), ("eq", "B")],
            products=["B_top"],
            equilibrators=["eq"],
        )
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 1.0, "B": 1.0}
        )
        rep = route_impurities(cfg, res, {"A": {"He4": 0.2}})
        r = rep.routes[0]
        assert r.destination == "B_top"  # terminal of B
        assert r.path == ["A", "A_top", "eq", "B", "B_top"]
        assert "passes through eq" in r.basis

    def test_freeze_in_downstream_colder_column(self):
        # CO is non-condensable nowhere, but a vapour-borne species that
        # freezes downstream must deposit there, not at the entry column.
        cfg = _config(["A", "B"], [("A_top", "B"), ("B_top", "P")], products=["P"])
        windows = {"A": (300.0, 310.0), "B": (60.0, 70.0)}  # CO: K=inf at 305 K?
        res = _FakeFlowsheetResult(windows, {"A": 1.0, "B": 1.0})
        # 300-310 K is above CO's T_c (132.86 K) -> non-condensable at A,
        # but B's window (60-70 K) is above CO's T_tp yet below T_c ->
        # vle_active there (no freeze); CH4 (T_tp = 90.69 K) freezes in B
        # only if the window minimum is below its triple point.
        windows["B"] = (80.0, 95.0)
        res = _FakeFlowsheetResult(windows, {"A": 1.0, "B": 1.0})
        rep = route_impurities(cfg, res, {"A": {"CH4": 0.5}})
        assert rep.routes[0].status == "frozen"
        assert rep.routes[0].destination == "B"

    def test_recirculating_loop_is_caught(self):
        cfg = _config(["A", "B"], [("A_top", "B"), ("B_top", "A")], products=[])
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 1.0, "B": 1.0}
        )
        rep = route_impurities(cfg, res, {"A": {"He4": 0.1}})
        assert rep.routes[0].status == "recirculating"
        assert "accumulates" in rep.routes[0].basis

    def test_splitter_ratio_applied(self):
        cfg = _config(
            ["A", "B", "C"],
            [("A_top", "B"), ("A_top", "C"), ("B_top", "PB"), ("C_top", "PC")],
            products=["PB", "PC"],
            splitter={"A_top": {"B": 0.25, "C": 0.75}},
        )
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW, "C": ISS_WINDOW},
            {"A": 1.0, "B": 1.0, "C": 1.0},
        )
        rep = route_impurities(cfg, res, {"A": {"He4": 1.0}})
        dests = {r.destination: r.flow_mol_h for r in rep.routes}
        assert dests == {"PB": 0.25, "PC": 0.75}
        assert all("splitter ratio" in r.basis for r in rep.routes)

    def test_multiple_destinations_without_splitter_flags_note(self):
        cfg = _config(
            ["A", "B", "C"],
            [("A_top", "B"), ("A_top", "C"), ("B_top", "PB"), ("C_top", "PC")],
            products=["PB", "PC"],
        )
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW, "C": ISS_WINDOW},
            {"A": 1.0, "B": 1.0, "C": 1.0},
        )
        rep = route_impurities(cfg, res, {"A": {"He4": 1.0}})
        assert all(r.flow_mol_h == pytest.approx(1.0) for r in rep.routes)
        assert all("no splitter ratio configured" in r.basis for r in rep.routes)

    def test_report_dict_and_aggregations(self):
        cfg = _config(["A"], [], products=["A_top"])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4, "CO": 0.8}})
        assert rep.by_destination()["A_top"] == {"He4": pytest.approx(0.4)}
        assert rep.by_destination()["A"] == {"CO": pytest.approx(0.8)}
        d = rep.to_dict()
        assert set(d) == {
            "routes",
            "by_destination",
            "by_status",
            "purge_designs",
            "warnings",
        }

    def test_errors(self):
        cfg = _config(["A"], [], products=[])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 1.0})
        with pytest.raises(KeyError, match="no solved result"):
            route_impurities(cfg, res, {"ZZ": {"He4": 1.0}})
        with pytest.raises(KeyError, match="not impurity species"):
            route_impurities(cfg, res, {"A": {"Ar": 1.0}})

    def test_purge_diverts_helium_from_the_top_product(self):
        # V1.2: the condenser purge takes the helium, the top product
        # stays clean -- provided the vent pressure is known
        cfg = _config(["A"], [], products=["A_top"])
        cfg.columns[0].pressure_top_Pa = 90_000.0
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        spec = PurgeSpec("A", 0.2)
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4}}, purges={"A": spec})
        he = [r for r in rep.routes if r.species == "He4"]
        assert len(he) == 1
        assert he[0].status == "purge"
        assert he[0].destination == "A_purge"
        assert "A_top" not in [r.destination for r in rep.routes]
        design = rep.purge_designs["A"]
        assert design.he_flow_mol_h == pytest.approx(0.4)
        assert design.loss_total_mol_h == pytest.approx(0.4 * 4.0, rel=1e-9)
        assert rep.to_dict()["purge_designs"]["A"]["he_enrichment"] == 0.2

    def test_purge_combines_multiple_helium_isotopes(self):
        cfg = _config(["A"], [], products=["A_top"])
        cfg.columns[0].pressure_top_Pa = 90_000.0
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        rep = route_impurities(
            cfg,
            res,
            {"A": {"He3": 0.1, "He4": 0.3}},
            purges={"A": PurgeSpec("A", 0.25)},
        )
        # one design, fed by the summed helium flow -- not two designs
        assert set(rep.purge_designs) == {"A"}
        assert rep.purge_designs["A"].he_flow_mol_h == pytest.approx(0.4)
        assert {r.species for r in rep.routes} == {"He3", "He4"}

    def test_downstream_purge_uses_actual_arrival_flow(self):
        # helium injected at A leaves through B's purge: the design must be
        # driven by the flow that really arrives at B
        cfg = _config(["A", "B"], [("A_top", "B")], products=["B_top"])
        cfg.columns[1].pressure_top_Pa = 90_000.0
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 1.0, "B": 1.0}
        )
        rep = route_impurities(
            cfg, res, {"A": {"He4": 0.4}}, purges={"B": PurgeSpec("B", 0.2)}
        )
        assert rep.routes[0].destination == "B_purge"
        assert rep.routes[0].path == ["A", "A_top", "B", "B_purge"]
        assert rep.purge_designs["B"].he_flow_mol_h == pytest.approx(0.4)

    def test_purge_never_designed_for_phantom_helium(self):
        # A's purge removes the helium -> B's purge sees nothing and gets
        # no design (and no division by zero)
        cfg = _config(["A", "B"], [("A_top", "B")], products=["B_top"])
        cfg.columns[0].pressure_top_Pa = 90_000.0
        cfg.columns[1].pressure_top_Pa = 90_000.0
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 1.0, "B": 1.0}
        )
        rep = route_impurities(
            cfg,
            res,
            {"A": {"He4": 0.4}},
            purges={"A": PurgeSpec("A", 0.2), "B": PurgeSpec("B", 0.2)},
        )
        assert set(rep.purge_designs) == {"A"}

    def test_frozen_species_raises_visible_warning(self):
        cfg = _config(["A"], [], products=[])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 1.0})
        with pytest.warns(UserWarning, match="FREEZE OUT"):
            rep = route_impurities(cfg, res, {"A": {"CO": 0.8}})
        assert any("FREEZE OUT" in w for w in rep.warnings)


# ----------------------------------------------------------------------
# integration: real ISS-I cascade (CasADi)
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def iss_i_solved():
    pytest.importorskip("casadi")
    from h2iso.flowsheet.schema import load_flowsheet
    from h2iso.flowsheet.solver import SequentialModularSolver

    config = load_flowsheet(FIXTURE_DIR / "iss_i.json")
    solver = SequentialModularSolver(config, method="wegstein", continuation_substeps=3)
    result = solver.solve(max_iter=50, tol=1e-4)
    assert result.converged, "ISS-I base case must converge before routing"
    return config, result


class TestIssiIntegration:
    """CFEDR ISS-I: the reference impurity recipe injected at CD2."""

    INJECTION = {"CD2": {"CO": 0.80357, "N2": 0.40179, "He4": 0.40179}}

    def _routes(self, iss_i_solved):
        import warnings

        config, result = iss_i_solved
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return route_impurities(config, result, self.INJECTION)

    def test_helium_leaves_with_cd2_top_product(self, iss_i_solved):
        # ISS-I: CD2 top is the WDS-D product (D2-rich waste) -- no
        # downstream column, so He contaminates that product stream.
        he = [r for r in self._routes(iss_i_solved).routes if r.species == "He4"]
        assert len(he) == 1
        assert he[0].status == "vent"
        assert he[0].destination == "CD2_top"
        assert he[0].path == ["CD2", "CD2_top"]

    def test_co_and_n2_deposit_in_cd2(self, iss_i_solved):
        frozen = self._routes(iss_i_solved).frozen_columns()
        assert set(frozen) == {"CD2"}
        assert frozen["CD2"]["CO"] == pytest.approx(0.80357, rel=1e-6)
        assert frozen["CD2"]["N2"] == pytest.approx(0.401785, rel=1e-3)

    def test_totals_conserve_the_injection(self, iss_i_solved):
        rep = self._routes(iss_i_solved)
        for sp, flow in self.INJECTION["CD2"].items():
            routed = sum(r.flow_mol_h for r in rep.routes if r.species == sp)
            assert routed == pytest.approx(flow, rel=1e-9)


class TestInjectionValidation:
    """T-3.4: injected impurity flows are validated before the scaling step.

    The injection vector is normalised by its own total; negative or
    non-finite entries made that normalisation meaningless (mixed-sign input
    divided by a zero total, ``nan`` propagated into every routed flow).
    """

    def _cfg_res(self):
        cfg = _config(["A", "B"], [("A_top", "B")], products=["B_top"])
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 5.0, "B": 5.0}
        )
        return cfg, res

    def test_mixed_sign_injection_rejected(self):
        cfg, res = self._cfg_res()
        with pytest.raises(ValueError, match="injected"):
            route_impurities(cfg, res, {"A": {"He4": 1.0, "CO": -1.0}})

    def test_all_negative_injection_rejected(self):
        cfg, res = self._cfg_res()
        with pytest.raises(ValueError, match="injected"):
            route_impurities(cfg, res, {"A": {"He4": -0.4, "CO": -0.6}})

    def test_nan_injection_rejected(self):
        cfg, res = self._cfg_res()
        with pytest.raises(ValueError, match="injected"):
            route_impurities(cfg, res, {"A": {"He4": float("nan")}})

    def test_inf_injection_rejected(self):
        cfg, res = self._cfg_res()
        with pytest.raises(ValueError, match="injected"):
            route_impurities(cfg, res, {"A": {"He4": float("inf")}})

    def test_clean_injection_still_conserves(self):
        cfg, res = self._cfg_res()
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4, "He3": 0.15}})
        assert len(rep.routes) == 2
        assert sum(r.flow_mol_h for r in rep.routes) == pytest.approx(0.55, rel=1e-12)


# ----------------------------------------------------------------------
# D1(a): terminal-stream semantics (product / unconnected / purge)
# ----------------------------------------------------------------------
#
# ``status == "vent"`` only means "reached a terminal stream".  It does NOT
# mean "entered a vent/purge branch", and ``ImpurityRoute.enters_vent`` is
# misleading: it returns True for ``product`` termini but False for real
# condenser purge branches.  These tests pin the unambiguous replacement
# fields.  The legacy attribute is left untouched on purpose (an API change
# would need its own decision) -- it is only documented as deprecated.


class TestTerminalKindSemantics:
    def test_declared_product_terminal(self):
        cfg = _config(["A", "B"], [("A_top", "B")], products=["B_top"])
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW}, {"A": 5.0, "B": 5.0}
        )
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4}})
        r = rep.routes[0]
        assert r.status == "vent"
        assert r.terminal_kind == "declared_product_end"
        assert r.exits_via_terminal_stream is True
        assert r.enters_purge_branch is False
        # legacy field: unchanged, and it does not distinguish product/purge
        assert r.enters_vent is True

    def test_unconnected_terminal_stream(self):
        # A_top is a leaf but is NOT a declared product
        cfg = _config(["A"], [], products=[])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        r = route_impurities(cfg, res, {"A": {"He4": 0.4}}).routes[0]
        assert r.status == "vent"
        assert r.terminal_kind == "undeclared_terminal_end"
        assert r.exits_via_terminal_stream is True
        assert r.enters_purge_branch is False

    def test_purge_branch_is_the_only_purge_terminal(self):
        cfg = _config(["A"], [], products=["A_top"])
        cfg.columns[0].pressure_top_Pa = 90_000.0
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        rep = route_impurities(
            cfg, res, {"A": {"He4": 0.4}}, purges={"A": PurgeSpec("A", 0.2)}
        )
        r = rep.routes[0]
        assert r.status == "purge"
        assert r.terminal_kind == "purge_branch"
        assert r.enters_purge_branch is True
        assert r.exits_via_terminal_stream is False
        # the trap this whole task exists for: the legacy flag is False for a
        # REAL purge branch, yet True for a plain product stream
        assert r.enters_vent is False

    def test_non_terminal_routes_carry_no_terminal_kind(self):
        cfg = _config(["A"], [], products=[])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 1000.0})
        rep = route_impurities(cfg, res, {"A": {"N2": 1.0e-3}})
        assert rep.routes, "expected dissolved + frozen routes"
        for r in rep.routes:
            assert r.status in {"dissolved", "frozen"}
            assert r.terminal_kind is None
            assert r.exits_via_terminal_stream is False
            assert r.enters_purge_branch is False

    def test_terminal_kind_covers_every_stream_terminus(self):
        # invariant: a route that ends on a stream carries a kind; the legacy
        # status and the new kind can never contradict each other
        cfg = _config(
            ["A", "B", "C"], [("A_top", "B"), ("B_top", "C")], products=["C_top"]
        )
        cfg.columns[1].pressure_top_Pa = 90_000.0
        res = _FakeFlowsheetResult(
            {"A": ISS_WINDOW, "B": ISS_WINDOW, "C": ISS_WINDOW},
            {"A": 1.0, "B": 1.0, "C": 1.0},
        )
        rep = route_impurities(
            cfg, res, {"A": {"He4": 0.4}}, purges={"B": PurgeSpec("B", 0.2)}
        )
        assert rep.routes
        for r in rep.routes:
            if r.status == "vent":
                assert r.terminal_kind in {
                    "declared_product_end",
                    "undeclared_terminal_end",
                }
            elif r.status == "purge":
                assert r.terminal_kind == "purge_branch"
            else:
                assert r.terminal_kind is None
            assert not (r.exits_via_terminal_stream and r.enters_purge_branch)

    def test_to_dict_exposes_terminal_kind_and_report_keys_are_stable(self):
        cfg = _config(["A"], [], products=["A_top"])
        res = _FakeFlowsheetResult({"A": ISS_WINDOW}, {"A": 5.0})
        rep = route_impurities(cfg, res, {"A": {"He4": 0.4}})
        assert rep.routes[0].to_dict()["terminal_kind"] == "declared_product_end"
        assert set(rep.to_dict()) == {
            "routes",
            "by_destination",
            "by_status",
            "purge_designs",
            "warnings",
        }
