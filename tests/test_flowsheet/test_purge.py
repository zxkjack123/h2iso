"""Non-condensable purge branch tests -- the V1.2 scheme.

Physics locked in here:

1. the condensable loss per mole of helium equals ``(1 - y_He)/y_He``
   exactly (the equilibrium vent is stage-count independent);
2. higher helium enrichment needs a colder vent point and loses less;
3. the vent may not fall through the freezing floor of the condensate --
   the floor caps the enrichment, and raising the vent pressure widens
   the window;
4. tritium accounting counts T atoms (HT/DT = 1, T2 = 2).

Plus the routing integration: helium is diverted to ``{column}_purge``,
the design uses the helium flow that actually arrives (a purge downstream
of another purge is never designed for phantom helium).
"""

from __future__ import annotations

import numpy as np
import pytest

from h2iso.purge import (
    PurgeSpec,
    design_purge,
    max_feasible_enrichment,
    sweep_purge,
)
from h2iso.species import SPECIES_ORDER, species_index

P_TOP = 90_000.0
T_TOP = 23.605  # CD2 condenser temperature from the ISS-I solve
PURE_D2_TTP = 18.72
PURE_T2_TTP = 20.62


class _FakeColumn:
    """A solved-column stand-in: pure-D2 top at ``T_top``."""

    def __init__(self, x=None, t_top=T_TOP):
        self.x_profile = np.array([x if x is not None else _pure("D2")])
        self.T_profile = np.array([t_top, t_top + 1.0])


def _pure(species):
    x = np.zeros(len(SPECIES_ORDER))
    x[species_index(species)] = 1.0
    return x


def _mix(**fracs):
    x = np.zeros(len(SPECIES_ORDER))
    for sp, f in fracs.items():
        x[species_index(sp)] = f
    return x / x.sum()


class TestPurgePhysics:
    def test_loss_ratio_identity(self):
        col = _FakeColumn()
        for y in (0.1, 0.2, 0.35, 0.5):
            d = design_purge(col, 0.4, PurgeSpec("CD2", y), pressure_Pa=P_TOP)
            assert d.loss_per_he_mol == pytest.approx((1 - y) / y, rel=1e-9)

    def test_enrichment_needs_subcooling(self):
        col = _FakeColumn()
        d = design_purge(col, 0.4, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP)
        assert d.T_vent_K < d.T_condenser_K
        assert d.subcooling_K == pytest.approx(T_TOP - d.T_vent_K)
        assert d.subcooling_K > 0.1

    def test_higher_enrichment_colder_and_cheaper(self):
        col = _FakeColumn()
        designs = sweep_purge(
            col, 0.4, PurgeSpec("CD2", 0.2), (0.1, 0.2, 0.3, 0.45), pressure_Pa=P_TOP
        )
        temps = [d.T_vent_K for d in designs]
        losses = [d.loss_total_mol_h for d in designs]
        assert temps == sorted(temps, reverse=True)  # colder as y grows
        assert losses == sorted(losses, reverse=True)  # cheaper as y grows

    def test_freeze_floor_caps_enrichment(self):
        col = _FakeColumn()  # pure D2 -> floor 18.72 K
        y_max = max_feasible_enrichment(col, PurgeSpec("CD2", 0.5), pressure_Pa=P_TOP)
        ok = design_purge(col, 0.4, PurgeSpec("CD2", y_max - 0.02), pressure_Pa=P_TOP)
        bad = design_purge(col, 0.4, PurgeSpec("CD2", y_max + 0.02), pressure_Pa=P_TOP)
        assert ok.feasible and not bad.feasible
        assert bad.limiting_species == "D2"
        assert bad.floor_K == pytest.approx(PURE_D2_TTP, abs=0.01)
        assert "INFEASIBLE" in bad.basis

    def test_t2_top_sets_a_higher_floor(self):
        col = _FakeColumn(x=_mix(T2=0.30, DT=0.40, HT=0.30))
        y_max = max_feasible_enrichment(col, PurgeSpec("CD2", 0.5), pressure_Pa=P_TOP)
        d = design_purge(col, 0.4, PurgeSpec("CD2", y_max + 0.05), pressure_Pa=P_TOP)
        assert d.limiting_species == "T2"
        assert d.floor_K == pytest.approx(PURE_T2_TTP, abs=0.01)

    def test_higher_pressure_widens_the_window(self):
        col = _FakeColumn()
        y_low = max_feasible_enrichment(
            col, PurgeSpec("CD2", 0.5), pressure_Pa=90_000.0
        )
        y_high = max_feasible_enrichment(
            col, PurgeSpec("CD2", 0.5), pressure_Pa=200_000.0
        )
        assert y_high > y_low

    def test_margin_shrinks_the_window(self):
        col = _FakeColumn()
        y0 = max_feasible_enrichment(
            col, PurgeSpec("CD2", 0.5, margin_K=0.0), pressure_Pa=P_TOP
        )
        y1 = max_feasible_enrichment(
            col, PurgeSpec("CD2", 0.5, margin_K=1.0), pressure_Pa=P_TOP
        )
        assert y1 < y0

    def test_tritium_accounting_counts_atoms(self):
        col = _FakeColumn(x=_mix(D2=0.5, DT=0.3, T2=0.2))
        d = design_purge(col, 1.0, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP)
        loss = d.condensable_loss_mol_h
        expected = loss.get("HT", 0.0) + loss.get("DT", 0.0) + 2 * loss.get("T2", 0.0)
        assert d.tritium_loss_mol_h == pytest.approx(expected, rel=1e-12)
        assert d.tritium_loss_mol_h > 0

    def test_loss_scales_with_helium_flow(self):
        col = _FakeColumn()
        d1 = design_purge(col, 0.4, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP)
        d2 = design_purge(col, 0.8, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP)
        assert d2.loss_total_mol_h == pytest.approx(2 * d1.loss_total_mol_h, rel=1e-12)
        assert d1.fraction_of_distillate is None  # no product flow given

    def test_fraction_of_distillate_reported(self):
        col = _FakeColumn()
        d = design_purge(
            col, 0.4, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP, product_flow_mol_h=18.3
        )
        assert d.fraction_of_distillate == pytest.approx(d.loss_total_mol_h / 18.3)

    def test_dict_roundtrip(self):
        col = _FakeColumn()
        d = design_purge(col, 0.4, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP)
        assert d.to_dict()["he_enrichment"] == 0.2
        assert d.to_dict()["loss_per_he_mol"] == pytest.approx(4.0, rel=1e-9)

    def test_errors(self):
        col = _FakeColumn()
        with pytest.raises(ValueError, match="he_enrichment"):
            PurgeSpec("CD2", 0.0)
        with pytest.raises(ValueError, match="he_enrichment"):
            PurgeSpec("CD2", 1.5)
        with pytest.raises(ValueError, match="margin_K"):
            PurgeSpec("CD2", 0.2, margin_K=-1.0)
        with pytest.raises(ValueError, match="vent pressure required"):
            design_purge(col, 0.4, PurgeSpec("CD2", 0.2))
        with pytest.raises(ValueError, match="he_flow_mol_h"):
            design_purge(col, -1.0, PurgeSpec("CD2", 0.2), pressure_Pa=P_TOP)
