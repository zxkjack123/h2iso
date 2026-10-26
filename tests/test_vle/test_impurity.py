"""Impurity extension tests (declared demonstration fixture).

Covers (acceptance: >= 10 new tests, all traceable to NIST-based values):

1. Registry: 5 impurities, 11-component combined order, stable indices
2. Normal boiling points reproduced from the (fitted) vapour pressures
3. Solid-phase semantics below the triple point (CO / CH4 / N2)
4. He-3 EPT-76 saturation (NBP + critical point) and non-condensable rule
5. K-value rules (inf for supercritical / He; SolidPhaseError in-window)
6. Rachford-Rice with K = inf: mass balance, He-all-vapour, consistency
   with the classic solver when all K are finite
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

pytest.importorskip("casadi")  # importing h2iso pulls in the CasADi solver layer

from h2iso.impurities import (
    ALL_SPECIES_ORDER,
    IMPURITY_ORDER,
    N_ALL_SPECIES,
    SolidPhaseError,
    check_feed_impurities,
    column_impurity_disposition,
    dilute_top_product,
    has_solid_phase,
    is_non_condensable,
    kvalue_impurity,
    pvap_impurity,
    species_index_all,
)
from h2iso.vle.mixing import rachford_rice, rachford_rice_extended

P_ATM = 101325.0


class TestRegistry:
    def test_impurity_order(self):
        assert IMPURITY_ORDER == ["CO", "CH4", "N2", "He3", "He4"]

    def test_combined_order_11(self):
        assert N_ALL_SPECIES == 11
        assert ALL_SPECIES_ORDER[:6] == ["H2", "HD", "HT", "D2", "DT", "T2"]
        assert ALL_SPECIES_ORDER[6:] == IMPURITY_ORDER

    def test_index_lookup(self):
        assert species_index_all("H2") == 0
        assert species_index_all("He4") == 10
        assert species_index_all("CO") == 6

    def test_solid_phase_flags(self):
        assert has_solid_phase("CO")
        assert has_solid_phase("CH4")
        assert has_solid_phase("N2")
        assert not has_solid_phase("He3")
        assert not has_solid_phase("He4")


class TestBoilingPoints:
    """pvap at the NIST normal boiling points should recover 1 atm."""

    @pytest.mark.parametrize(
        "species, t_b",
        [("CO", 81.639), ("CH4", 111.669), ("N2", 77.356)],
    )
    def test_impurity_nbp(self, species, t_b):
        p = pvap_impurity(t_b, species)
        assert p == pytest.approx(P_ATM, rel=0.01)

    def test_he4_nbp(self):
        p = pvap_impurity(4.224, "He4")
        assert p == pytest.approx(P_ATM, rel=0.02)

    def test_he3_nbp_and_critical(self):
        # EPT-76 equation: both anchors must reproduce
        assert pvap_impurity(3.1968, "He3") == pytest.approx(P_ATM, rel=0.01)
        p_c = 1.1466e5  # P_c = 114.66 kPa
        assert pvap_impurity(3.3157, "He3") == pytest.approx(p_c, rel=0.02)


class TestSolidPhaseSemantics:
    def test_co_solid_in_iss_window(self):
        with pytest.raises(SolidPhaseError, match="CO"):
            pvap_impurity(23.0, "CO")

    def test_n2_solid_in_iss_window(self):
        with pytest.raises(SolidPhaseError, match="N2"):
            pvap_impurity(25.0, "N2")

    def test_ch4_solid_in_iss_window(self):
        with pytest.raises(SolidPhaseError, match="CH4"):
            pvap_impurity(25.0, "CH4")

    def test_liquid_region_ok_above_triple_point(self):
        # just above the triple points: finite, tiny pressures
        assert pvap_impurity(68.5, "CO") == pytest.approx(15538.0 * 1.03, rel=0.1)
        assert pvap_impurity(64.0, "N2") > 0


class TestNonCondensableRules:
    def test_helium_supercritical_in_window(self):
        for T in (19.0, 25.0, 30.0):
            assert is_non_condensable(T, "He3")
            assert is_non_condensable(T, "He4")

    def test_kvalue_helium_is_inf(self):
        assert math.isinf(kvalue_impurity(25.0, 95000.0, "He3"))
        assert math.isinf(kvalue_impurity(25.0, 95000.0, "He4"))

    def test_co_supercritical_above_critical(self):
        assert is_non_condensable(140.0, "CO")  # T_c = 132.86 K
        assert math.isinf(kvalue_impurity(140.0, 95000.0, "CO"))

    def test_kvalue_solid_raises_in_window(self):
        with pytest.raises(SolidPhaseError):
            kvalue_impurity(25.0, 95000.0, "CO")


class TestRachfordRiceExtended:
    def test_all_condensable_matches_classic(self):
        z = np.array([0.5, 0.3, 0.2])
        K = np.array([4.0, 1.0, 0.3])
        v_ext, x_ext, y_ext = rachford_rice_extended(z, K)
        v_cls = rachford_rice(z, K)
        assert v_ext == pytest.approx(v_cls, abs=1e-8)

    def test_helium_goes_fully_vapor(self):
        # 20% non-condensable: below the dew point of the rest -> all vapour
        z = np.array([0.5, 0.3, 0.2])
        K = np.array([2.0, 0.5, math.inf])
        v, x, y = rachford_rice_extended(z, K)
        assert v == pytest.approx(1.0)
        assert x[2] == 0.0
        assert y[2] == pytest.approx(0.2)

    def test_two_phase_mass_balance_with_kinf(self):
        z = np.array([0.5, 0.4, 0.1])
        K = np.array([5.0, 0.2, math.inf])
        v, x, y = rachford_rice_extended(z, K)
        assert 0.1 < v < 1.0  # above Z_inf, two phase
        assert x[2] == 0.0
        assert y[2] == pytest.approx(0.1 / v)
        # component mass balance: z_i = (1 - V) x_i + V y_i
        assert np.allclose((1 - v) * x + v * y, z, atol=1e-10)
        assert x.sum() == pytest.approx(1.0)
        assert y.sum() == pytest.approx(1.0)

    def test_fully_non_condensable_feed(self):
        z = np.array([0.6, 0.4])
        K = np.array([math.inf, math.inf])
        v, x, y = rachford_rice_extended(z, K)
        assert v == pytest.approx(1.0)
        assert np.allclose(y, z)

    def test_invalid_inputs(self):
        with pytest.raises(ValueError, match="NaN"):
            rachford_rice_extended(np.array([0.5, 0.5]), np.array([1.0, np.nan]))
        with pytest.raises(ValueError, match="non-negative"):
            rachford_rice_extended(np.array([-0.1, 1.1]), np.array([1.0, 1.0]))
        with pytest.raises(ValueError, match="shape"):
            rachford_rice_extended(np.array([1.0]), np.array([1.0, 2.0]))

    # --- all-liquid (bubble guard) contract ------------------------------
    # Oracle: the classic solver short-circuits to exactly 0.0 whenever the
    # bubble criterion sum(z_i K_i) <= 1 holds (see rachford_rice :211).

    def test_subcooled_feed_is_all_liquid(self):
        """Sub-cooled feed (sum z K < 1) must be all liquid, V == 0.0."""
        z = np.array([0.5, 0.5])
        K = np.array([0.3, 0.6])
        assert float(np.sum(z * K)) < 1.0  # regime under test: sub-cooled
        v, x, y = rachford_rice_extended(z, K)
        assert v == 0.0
        assert np.allclose(x, z)
        assert not np.any(y)

    def test_at_bubble_point_is_all_liquid(self):
        """At the bubble point (sum z K == 1) the convention is V == 0.0."""
        z = np.array([0.5, 0.5])
        K = np.array([1.5, 0.5])
        assert abs(float(np.sum(z * K)) - 1.0) <= 1e-15  # exactly on the bubble
        v, x, y = rachford_rice_extended(z, K)
        assert v == 0.0
        assert np.allclose(x, z)
        assert not np.any(y)

    def test_all_liquid_agrees_with_classic(self):
        """Fixed sub-cooled table: extended must equal classic exactly (0.0)."""
        cases = [
            (np.array([0.5, 0.5]), np.array([0.3, 0.6])),
            (np.array([0.4, 0.6]), np.array([0.2, 0.7])),
            (np.array([0.2, 0.8]), np.array([0.9, 0.5])),
            (np.array([0.1, 0.9]), np.array([1.2, 0.3])),
            (np.array([0.7, 0.3]), np.array([0.5, 0.8])),
            (np.array([0.5, 0.3, 0.2]), np.array([1.5, 0.5, 0.2])),
        ]
        for z, K in cases:
            assert np.all(np.isfinite(K))
            assert float(np.sum(z * K)) < 1.0
            v_ext = rachford_rice_extended(z, K)[0]
            v_cls = rachford_rice(z, K)
            assert v_ext == v_cls == 0.0

    # --- illegal K / feed validation -------------------------------------

    def test_negative_k_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            rachford_rice_extended(np.array([0.5, 0.5]), np.array([1.0, -2.0]))

    def test_negative_inf_k_rejected(self):
        with pytest.raises(ValueError):
            rachford_rice_extended(np.array([0.5, 0.5]), np.array([1.0, -math.inf]))

    def test_zero_k_is_all_liquid_and_warns_nothing(self):
        """K = 0 stays legal: it is a strongly condensing species."""
        z = np.array([0.5, 0.5])
        K = np.array([1.0, 0.0])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            v, x, y = rachford_rice_extended(z, K)
        assert v == 0.0
        assert np.allclose(x, z)
        assert not np.any(y)

    def test_z_sum_validated(self):
        z = np.array([0.5, 0.3, 0.2]) * 1.2
        K = np.array([4.0, 1.0, 0.3])
        assert abs(float(np.sum(z)) - 1.0) > 1e-6
        with pytest.raises(ValueError):
            rachford_rice_extended(z, K)


class TestFeedChecks:
    """Feed-level thresholds from the A.2 process answers (in code)."""

    def test_clean_feed(self):
        alerts = check_feed_impurities({})
        assert [a.code for a in alerts] == ["NO_IMPURITIES"]
        assert alerts[0].level == "info"

    def test_he_below_caution_no_he_alert(self):
        # 0.5 % He: below the 1 % caution limit -> only the interface note
        alerts = check_feed_impurities({"He4": 0.005})
        codes = [a.code for a in alerts]
        assert "HE_CAUTION" not in codes and "HE_UNACCEPTABLE" not in codes
        assert "INTERFACE_SPEC_EXCEEDED" in codes

    def test_he_caution_band(self):
        alerts = check_feed_impurities({"He4": 0.015, "N2": 0.002})
        he = [a for a in alerts if a.code == "HE_CAUTION"]
        assert len(he) == 1 and he[0].level == "warning"
        assert "condenser" in he[0].message

    def test_he_unacceptable_band(self):
        alerts = check_feed_impurities({"He3": 0.03, "He4": 0.03})
        codes = [a.code for a in alerts]
        assert "HE_UNACCEPTABLE" in codes
        assert "HE_CAUTION" not in codes  # the critical band supersedes
        assert any(a.level == "critical" for a in alerts)

    def test_declared_basis_feed_triggers_interface_note(self):
        # 1 % CO + 0.5 % N2 + 0.5 % He-4: 2e4 ppm >> 1 ppm interface spec
        alerts = check_feed_impurities({"CO": 0.01, "N2": 0.005, "He4": 0.005})
        codes = [a.code for a in alerts]
        assert "INTERFACE_SPEC_EXCEEDED" in codes
        assert "NO_IMPURITIES" not in codes

    def test_limits_override(self):
        alerts = check_feed_impurities({"He4": 0.005}, limits={"he_caution": 0.001})
        assert "HE_CAUTION" in [a.code for a in alerts]

    def test_unknown_species_rejected(self):
        with pytest.raises(KeyError, match="not impurity species"):
            check_feed_impurities({"Ar": 0.01})

    def test_alert_dict_roundtrip(self):
        a = check_feed_impurities({"He4": 0.06})[0]
        d = a.to_dict()
        assert d["level"] == "critical" and "message" in d


class TestRachfordRiceResidualContract:
    """Residual / differential contract for ``rachford_rice_extended``.

    The species material balance ``(1 - V) x + V y = z`` is *not* a
    discriminating check for this solver (it closes to a few 1e-7 even for the
    wrong branch), so the contract is stated on the Rachford-Rice residual

        h(V) = sum_finite z_i (K_i - 1) / (1 + V (K_i - 1)) + z_inf / V

    and, in the all-liquid endpoint where ``h`` is not defined, on the
    one-sided bubble slack ``sum(z_i K_i) - 1 <= 0``.
    """

    @staticmethod
    def _residual(z, K, v):
        z = np.asarray(z, dtype=float)
        K = np.asarray(K, dtype=float)
        mask = np.isposinf(K)
        zf, Kf, z_inf = z[~mask], K[~mask], float(np.sum(z[mask]))
        h = float(np.sum(zf * (Kf - 1.0) / (1.0 + v * (Kf - 1.0))))
        if z_inf > 0.0 and v > 0.0:
            h += z_inf / v
        return h

    def test_returned_root_has_small_residual(self):
        cases = [
            ("all_liquid sub-cooled", [0.5, 0.5], [0.3, 0.6], 0.0),
            ("all_liquid at bubble", [0.5, 0.5], [1.5, 0.5], 0.0),
            ("all_liquid ternary", [0.5, 0.3, 0.2], [1.5, 0.5, 0.2], 0.0),
            ("two_phase binary", [0.5, 0.5], [3.0, 0.3], None),
            ("two_phase with K=inf", [0.5, 0.4, 0.1], [2.0, 0.5, np.inf], None),
            ("all_vapour", [0.5, 0.5], [5.0, 5.0], 1.0),
        ]
        for label, z, K, expect_v in cases:
            z = np.array(z)
            K = np.array(K)
            v = rachford_rice_extended(z, K)[0]
            mask = np.isposinf(K)
            if expect_v == 0.0:
                # all liquid: the root is the endpoint, contract is the
                # one-sided bubble slack, not |sum(z K) - 1|
                assert v == 0.0, label
                slack = float(np.sum(z[~mask] * K[~mask])) - 1.0
                assert slack <= 1e-12, (label, slack)
            elif expect_v == 1.0:
                assert v == 1.0, label
                assert float(np.sum(z[~mask] / K[~mask])) <= 1.0, label
            else:
                assert abs(self._residual(z, K, v)) <= 1e-9, (
                    label,
                    self._residual(z, K, v),
                )

    def test_residual_contract_matches_classic_two_phase(self):
        z = np.array([0.5, 0.5])
        K = np.array([3.0, 0.3])
        v_ext = rachford_rice_extended(z, K)[0]
        v_cls = rachford_rice(z, K)
        assert 0.0 < v_ext < 1.0
        assert abs(v_ext - v_cls) <= 1e-9
        assert abs(self._residual(z, K, v_ext)) <= 1e-9


class TestFeedCheckInputValidation:
    """T-3.1: illegal impurity mole fractions are rejected at the entry point.

    Impurity fractions are non-negative finite quantities; ``NaN`` / ``+-inf``
    silently poison every downstream balance (``total``/``he`` sums become
    ``nan`` and every threshold comparison turns False).  ``0.0`` remains a
    legal (if vacuous) entry and must still take the clean-feed branch.
    """

    def test_negative_fraction_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            check_feed_impurities({"He4": -1e-3})

    def test_nan_fraction_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            check_feed_impurities({"He4": float("nan")})

    def test_non_finite_fraction_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            check_feed_impurities({"He4": float("inf")})

    def test_clean_feed_still_info(self):
        assert [a.code for a in check_feed_impurities({})] == ["NO_IMPURITIES"]
        assert [a.code for a in check_feed_impurities({"He4": 0.0})] == [
            "NO_IMPURITIES"
        ]


class TestDispositionInputValidation:
    """T-3.2: illegal disposition inputs are rejected, zero stays a skip.

    ``column_impurity_disposition`` previously let ``NaN`` straight through
    (``nan <= 0`` is False) and returned an ``ImpurityDisposition`` carrying a
    ``nan`` molar flow; a ``nan`` carrier flow poisoned the dissolved-trace cap
    in the same way.
    """

    T_MIN, T_MAX = 23.5, 24.9

    def test_disposition_nan_fraction_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            column_impurity_disposition(
                {"He4": float("nan")}, 10.0, self.T_MIN, self.T_MAX
            )

    def test_disposition_negative_fraction_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            column_impurity_disposition({"He4": -0.1}, 10.0, self.T_MIN, self.T_MAX)

    def test_disposition_feed_flow_nan_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            column_impurity_disposition(
                {"He4": 0.01}, float("nan"), self.T_MIN, self.T_MAX
            )

    def test_disposition_liquid_flow_nan_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            column_impurity_disposition(
                {"He4": 0.01},
                10.0,
                self.T_MIN,
                self.T_MAX,
                liquid_flow_mol_h=float("nan"),
            )

    def test_disposition_zero_fraction_skipped(self):
        assert (
            column_impurity_disposition({"He4": 0.0}, 10.0, self.T_MIN, self.T_MAX)
            == []
        )


class TestDiluteTopProductValidation:
    """T-3.3: illegal dilution inputs are rejected with named errors.

    ``dilute_top_product`` returned ``({'D2': nan, 'He4': nan}, nan)`` for a
    ``nan`` impurity flow, and an empty ``x_top`` died inside ``max()`` with the
    bare ``max() arg is an empty sequence`` message.
    """

    def test_dilute_nan_impurity_flow_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            dilute_top_product({"D2": 1.0}, {"He4": float("nan")}, 18.3)

    def test_dilute_negative_flow_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            dilute_top_product({"D2": 1.0}, {"He4": -1.0}, 18.3)

    def test_dilute_nan_fraction_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            dilute_top_product({"D2": float("nan")}, {"He4": 1e-6}, 18.3)

    def test_dilute_nan_distillate_rejected(self):
        with pytest.raises(ValueError, match="finite non-negative"):
            dilute_top_product({"D2": 1.0}, {"He4": 1e-6}, float("nan"))

    def test_dilute_empty_top_rejected(self):
        with pytest.raises(ValueError, match="at least one species"):
            dilute_top_product({}, {"He4": 0.1}, 18.3)

    def test_dilute_clean_case_unchanged(self):
        x_dil, rel = dilute_top_product(
            {"D2": 0.999966, "DT": 0.000034}, {"He4": 1e-6}, 100.0
        )
        assert set(x_dil) == {"D2", "DT", "He4"}
        assert sum(x_dil.values()) == pytest.approx(1.0)
        assert 0.0 < rel < 1e-6
