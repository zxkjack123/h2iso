"""Regression tests for the condenser-stage feed defect (PM T-4304).

Background
----------
``Column.build_nlp`` (``src/h2iso/mesh/column.py``) assembles one component
material balance per stage.  The reboiler branch (``j == N-1``) and the
internal branch (``1 <= j <= N-2``) both add the feed contribution
(``mb += f_flow * f_z[i]``).  The condenser branch (``j == 0``) did **not**:
it assembled ``V[1]*y[1]_i - (L[0] + D)*x[0]_i`` even when a feed was attached
to stage 1.

The omission is silent, not infeasible.  The last component's balance is
algebraically eliminated from the NLP because, under CMO plus the summation
constraints, ``sum_i MB_i == 0``.  With the stage-1 feed missing that identity
breaks (``sum_i MB_i == -F_total``), so the whole feed leaks into the dropped
component and IPOPT still reports ``Solve_Succeeded`` -- e.g. for a
``D2/DT/T2 = 0.90/0.07/0.03``, ``F = 100`` feed at stage 1 the products
contained *no* D2 at all (D2 balance ``-90`` mol/h ``= -F*z_D2``) and were
essentially pure T2.

The tests below are the discriminative (RED) checks for that defect: they FAIL
on the defective tree and PASS once the condenser balance accounts for its
feed, consistently with the reboiler and internal branches.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("casadi")

from h2iso.mesh.column import Column, ColumnSpec

# D2/DT/T2 feed used by the shipped CD2 fixture (tests/test_mesh/test_column.py).
_FEED = np.zeros(6)
_FEED[3] = 0.90  # D2
_FEED[4] = 0.07  # DT
_FEED[5] = 0.03  # T2

_F = 100.0
_DF = 0.90
_R = 5.0
_P = 101325.0
_N_STAGES = 15

_FED_COMPONENTS = tuple(i for i in range(6) if _FEED[i] > 0.0)


def _condenser_feed_spec() -> ColumnSpec:
    """15-stage column whose feed enters the total condenser (stage 1)."""
    return ColumnSpec(
        n_stages=_N_STAGES,
        feed_stage=1,
        feed_flow=_F,
        feed_composition=_FEED.copy(),
        pressure=_P,
        reflux_ratio=_R,
        distillate_to_feed=_DF,
    )


def _mass_balance_ok(balance: float, z_i: float, F: float) -> bool:
    """Per-component acceptance criterion (mirrors tests/test_mesh/test_column.py).

    ``|balance| <= max(1e-5 * F, 1e-4 * F * z_i)``: an absolute floor covering
    feed-absent components plus the original relative tolerance.
    """
    atol = 1e-5 * F
    rtol = 1e-4 * F * z_i
    return abs(balance) <= max(atol, rtol)


@pytest.fixture(scope="module")
def condenser_feed_result():
    """Solve the ``feed_stage == 1`` column once for the whole module."""
    result = Column(_condenser_feed_spec()).solve()
    return result


def test_condenser_feed_solve_succeeds(condenser_feed_result):
    """The stage-1-feed column must still be reported as solved."""
    info = condenser_feed_result.convergence_info
    assert info["success"], f"IPOPT failed: {info['status']}"


def test_condenser_feed_component_mass_balance(condenser_feed_result):
    """Every component closes when the feed enters the condenser.

    Defective tree: the D2 balance is ``-F*z_D2 = -90`` mol/h (the feed is
    absent from the products) -> the criterion rejects it and this test FAILS.
    """
    result = condenser_feed_result
    D = _DF * _F
    B = _F - D
    x_D = result.x_profile[0]
    x_B = result.x_profile[-1]

    for i in range(6):
        balance = D * x_D[i] + B * x_B[i] - _F * _FEED[i]
        assert _mass_balance_ok(balance, _FEED[i], _F), (
            f"component {i} mass balance failed for feed_stage=1: "
            f"balance={balance:.4e}, z_i={_FEED[i]:.3e}, F={_F:.3e}"
        )


def test_condenser_feed_is_not_silently_dropped(condenser_feed_result):
    """Fed components must actually appear in the products.

    This asserts the *defect signature* rather than the tolerance: on the
    defective tree the products were essentially pure T2 while every fed
    component vanished (``D*x_D + B*x_B ~ 0`` for D2 and DT).
    """
    result = condenser_feed_result
    D = _DF * _F
    B = _F - D
    x_D = result.x_profile[0]
    x_B = result.x_profile[-1]

    for i in _FED_COMPONENTS:
        recovered = D * x_D[i] + B * x_B[i]
        fed = _F * _FEED[i]
        assert recovered > 0.5 * fed, (
            f"component {i} was silently dropped at feed_stage=1: "
            f"recovered={recovered:.6e} mol/h vs fed={fed:.6e} mol/h"
        )


def test_condenser_stage_material_balance(condenser_feed_result):
    """The condenser stage itself balances the incoming vapor *plus* feed.

    Under the CMO convention ``L[0] = R*D + q*F`` and ``V[1] = (R+1)*D``
    (``q = 1``), the total-condenser balance is
    ``V[1]*y[1] + F*z = (L[0] + D)*x[0]``.

    Defective tree: the three fed components leave a residual of
    ``F*z_i`` (summed residual ``-F_total``) -> this test FAILS.
    """
    spec = _condenser_feed_spec()
    column = Column(spec)
    L, V = column._compute_flows()
    result = condenser_feed_result

    D = _DF * _F
    residual = (
        V[1] * result.y_profile[1] + _F * _FEED - (L[0] + D) * result.x_profile[0]
    )
    for i in range(6):
        assert abs(residual[i]) <= 1e-5 * _F, (
            f"condenser stage balance failed for component {i}: "
            f"residual={residual[i]:.4e} mol/h"
        )


def test_condenser_flow_convention_matches_feed_contribution():
    """Pin the CMO flow convention the condenser balance is written against.

    Adding the feed term to the condenser balance is *not* double counting:
    ``_compute_flows`` already routes the stage-1 feed liquid into ``L[0]``
    (``L[0] = R*D + q*F``), so the drum's total outflow is ``L[0] + D``.
    This guards the documented risk that the feed term could be counted twice.
    """
    L, V = Column(_condenser_feed_spec())._compute_flows()
    D = _DF * _F
    assert L[0] == pytest.approx(_R * D + _F)
    assert V[1] == pytest.approx((_R + 1) * D)
    assert L[-1] == pytest.approx(_F - D)


def test_noncondenser_feed_stages_unaffected():
    """A feed below the condenser (stage 8 fixture) keeps closing its balance.

    Guards the fix against collateral damage to the shipped feed-stage
    behaviour: only the ``j == 0`` branch gained a feed term.
    """
    spec = ColumnSpec(
        n_stages=_N_STAGES,
        feed_stage=8,
        feed_flow=_F,
        feed_composition=_FEED.copy(),
        pressure=_P,
        reflux_ratio=_R,
        distillate_to_feed=_DF,
    )
    result = Column(spec).solve()
    assert result.convergence_info["success"]

    D = _DF * _F
    B = _F - D
    x_D = result.x_profile[0]
    x_B = result.x_profile[-1]
    for i in range(6):
        balance = D * x_D[i] + B * x_B[i] - _F * _FEED[i]
        assert _mass_balance_ok(balance, _FEED[i], _F), (
            f"component {i} mass balance regressed for feed_stage=8: "
            f"balance={balance:.4e}"
        )
