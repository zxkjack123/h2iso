"""Tests for single-stage MESH equations."""

import time

import casadi as ca
import numpy as np

from h2iso.mesh.enthalpy import (
    liquid_enthalpy_numeric,
    liquid_enthalpy_sx,
    vapor_enthalpy_numeric,
    vapor_enthalpy_sx,
)
from h2iso.mesh.stage import Stage
from h2iso.species import SPECIES_ORDER
from h2iso.vle.souers import pvap


class TestStageEquationCount:
    """Verify correct number of equations."""

    def test_total_equations(self):
        """Should have 2*6 + 2 + 1 = 15 equations per stage."""
        assert Stage.N_EQ == 15

    def test_n_components(self):
        assert Stage.N_C == 6


class TestStageResidualAtSteadyState:
    """Verify residual = 0 at a known steady-state solution."""

    def _make_steady_state_values(self):
        """Create a consistent steady-state for a single D2/DT stage.

        For consistency: at the bubble point T for composition x at P,
        we have sum(K*x) = 1 and y = K*x (no normalization needed).
        """
        P = 90000.0
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        x /= np.sum(x)

        # Find T where sum(K(T)*x) = 1 (bubble point)
        from scipy.optimize import brentq

        def obj(T):
            Kx_sum = 0.0
            for i, sp in enumerate(SPECIES_ORDER):
                Kx_sum += (pvap(T, sp) / P) * x[i]
            return Kx_sum - 1.0

        T = brentq(obj, 20.0, 30.0, xtol=1e-10)

        # K-values at bubble point
        K = np.zeros(6)
        for i, sp in enumerate(SPECIES_ORDER):
            K[i] = pvap(T, sp) / P

        # y = K*x (sum(y)=1 by construction at bubble T)
        y = K * x

        L = 100.0
        V = 50.0
        F = 0.0
        z = np.zeros(6)
        Q = 0.0
        x_in = x.copy()
        y_in = y.copy()
        H_L = liquid_enthalpy_numeric(T, x)
        H_V = vapor_enthalpy_numeric(T, y)

        return {
            "T": T,
            "P": P,
            "x": x,
            "y": y,
            "L": L,
            "V": V,
            "F": F,
            "z": z,
            "Q": Q,
            "x_in": x_in,
            "y_in": y_in,
            "H_L": H_L,
            "H_V": H_V,
        }

    def test_residual_at_steady_state(self):
        """At steady state, all 15 residuals should be ~0."""
        vals = self._make_steady_state_values()
        stage = Stage(pressure=vals["P"])

        # Create CasADi symbols
        T = ca.SX.sym("T")
        x = ca.SX.sym("x", 6)
        y = ca.SX.sym("y", 6)
        L_in = ca.SX.sym("L_in")
        L_out = ca.SX.sym("L_out")
        V_in = ca.SX.sym("V_in")
        V_out = ca.SX.sym("V_out")
        x_in = ca.SX.sym("x_in", 6)
        y_in = ca.SX.sym("y_in", 6)
        F = ca.SX.sym("F")
        z = ca.SX.sym("z", 6)
        Q = ca.SX.sym("Q")
        H_L_in = ca.SX.sym("H_L_in")
        H_V_in = ca.SX.sym("H_V_in")
        H_L_out = ca.SX.sym("H_L_out")
        H_V_out = ca.SX.sym("H_V_out")
        H_F = ca.SX.sym("H_F")

        # Build residual
        res = stage.build_residual(
            T,
            x,
            y,
            L_in,
            L_out,
            V_in,
            V_out,
            x_in,
            y_in,
            F,
            z,
            Q,
            H_L_in,
            H_V_in,
            H_L_out,
            H_V_out,
            H_F,
        )

        assert res.shape == (15, 1)

        # Create function and evaluate at known solution
        all_inputs = ca.vertcat(
            T,
            x,
            y,
            L_in,
            L_out,
            V_in,
            V_out,
            x_in,
            y_in,
            F,
            z,
            Q,
            H_L_in,
            H_V_in,
            H_L_out,
            H_V_out,
            H_F,
        )
        f = ca.Function("stage", [all_inputs], [res])

        # Pack values
        input_vals = np.concatenate(
            [
                [vals["T"]],
                vals["x"],
                vals["y"],
                [vals["L"], vals["L"], vals["V"], vals["V"]],
                vals["x_in"],
                vals["y_in"],
                [vals["F"]],
                vals["z"],
                [vals["Q"]],
                [vals["H_L"], vals["H_V"], vals["H_L"], vals["H_V"]],
                [0.0],  # H_F (no feed)
            ]
        )

        res_val = np.array(f(input_vals)).flatten()

        # All residuals should be near zero
        # Note: summation may have small error due to y normalization
        assert np.max(np.abs(res_val)) < 1e-8, (
            f"Max residual: {np.max(np.abs(res_val)):.2e}\nResiduals: {res_val}"
        )

    def test_jacobian_nonsingular(self):
        """Jacobian of residual w.r.t. stage variables should be non-singular."""
        stage = Stage(pressure=90000.0)

        # Stage variables: T, x(6), y(6) = 13 variables
        # (L, V are treated as knowns from the tridiagonal structure)
        T = ca.SX.sym("T")
        x = ca.SX.sym("x", 6)
        y = ca.SX.sym("y", 6)

        # Fixed parameters for this test
        L_in = ca.SX(100.0)
        L_out = ca.SX(100.0)
        V_in = ca.SX(50.0)
        V_out = ca.SX(50.0)
        x_in = ca.SX.sym("x_in", 6)  # parameters, not variables
        y_in = ca.SX.sym("y_in", 6)
        F = ca.SX(0.0)
        z = ca.SX.zeros(6)
        Q = ca.SX(0.0)

        # Use symbolic enthalpies
        H_L_in = liquid_enthalpy_sx(T, x_in)
        H_V_in = vapor_enthalpy_sx(T, y_in)
        H_L_out = liquid_enthalpy_sx(T, x)
        H_V_out = vapor_enthalpy_sx(T, y)
        H_F = ca.SX(0.0)

        res = stage.build_residual(
            T,
            x,
            y,
            L_in,
            L_out,
            V_in,
            V_out,
            x_in,
            y_in,
            F,
            z,
            Q,
            H_L_in,
            H_V_in,
            H_L_out,
            H_V_out,
            H_F,
        )

        # Jacobian w.r.t. T, x, y (13 variables → 15 equations)
        # But we have 15 equations, so we need 15 variables.
        # Include L_out, V_out as variables for a square system
        vars_vec = ca.vertcat(T, x, y)  # 13 vars for 15 eq → not square
        # For condition number test, use just equilibrium + summation (8 eq, 13 vars)
        # Actually let's compute Jacobian for the 13x15 and check it's full rank
        J = ca.jacobian(res, vars_vec)
        J_func = ca.Function("J", [vars_vec, x_in, y_in], [J])

        # Evaluate at a test point
        vals = self._make_steady_state_values()
        var_vals = np.concatenate([[vals["T"]], vals["x"], vals["y"]])
        J_num = np.array(J_func(var_vals, vals["x_in"], vals["y_in"]))

        # Check rank = 13 (full column rank since we have 15 rows, 13 cols)
        rank = np.linalg.matrix_rank(J_num, tol=1e-8)
        assert rank == 13, f"Jacobian rank = {rank}, expected 13 (full column rank)"

    def _make_steady_state_values(self):
        """Create steady-state values (same as above)."""
        P = 90000.0
        x = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        x /= np.sum(x)

        from scipy.optimize import brentq

        def obj(T):
            Kx_sum = 0.0
            for i, sp in enumerate(SPECIES_ORDER):
                Kx_sum += (pvap(T, sp) / P) * x[i]
            return Kx_sum - 1.0

        T = brentq(obj, 20.0, 30.0, xtol=1e-10)
        K = np.zeros(6)
        for i, sp in enumerate(SPECIES_ORDER):
            K[i] = pvap(T, sp) / P
        y = K * x
        L = 100.0
        V = 50.0
        x_in = x.copy()
        y_in = y.copy()
        H_L = liquid_enthalpy_numeric(T, x)
        H_V = vapor_enthalpy_numeric(T, y)
        return {
            "T": T,
            "P": P,
            "x": x,
            "y": y,
            "L": L,
            "V": V,
            "F": 0.0,
            "z": np.zeros(6),
            "Q": 0.0,
            "x_in": x_in,
            "y_in": y_in,
            "H_L": H_L,
            "H_V": H_V,
        }


class TestSymbolicGraphTiming:
    """Verify CasADi symbolic graph builds quickly."""

    def test_build_time_under_1s(self):
        """Symbolic graph construction should take < 1s."""
        t0 = time.perf_counter()

        stage = Stage(pressure=90000.0)
        T = ca.SX.sym("T")
        x = ca.SX.sym("x", 6)
        y = ca.SX.sym("y", 6)
        L_in = ca.SX.sym("L_in")
        L_out = ca.SX.sym("L_out")
        V_in = ca.SX.sym("V_in")
        V_out = ca.SX.sym("V_out")
        x_in = ca.SX.sym("x_in", 6)
        y_in = ca.SX.sym("y_in", 6)
        F = ca.SX.sym("F")
        z = ca.SX.sym("z", 6)
        Q = ca.SX.sym("Q")
        H_L_in = liquid_enthalpy_sx(T, x_in)
        H_V_in = vapor_enthalpy_sx(T, y_in)
        H_L_out = liquid_enthalpy_sx(T, x)
        H_V_out = vapor_enthalpy_sx(T, y)
        H_F = ca.SX(0.0)

        res = stage.build_residual(
            T,
            x,
            y,
            L_in,
            L_out,
            V_in,
            V_out,
            x_in,
            y_in,
            F,
            z,
            Q,
            H_L_in,
            H_V_in,
            H_L_out,
            H_V_out,
            H_F,
        )

        # Also build Jacobian
        vars_vec = ca.vertcat(T, x, y)
        J = ca.jacobian(res, vars_vec)
        ca.Function(
            "stage_with_jac",
            [vars_vec, x_in, y_in, L_in, V_in, L_out, V_out, F, z, Q],
            [res, J],
        )

        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"Build time: {elapsed:.2f}s (should be < 1s)"


class TestEnthalpy:
    """Test enthalpy functions."""

    def test_vapor_enthalpy_positive_above_ref(self):
        """Vapor enthalpy above reference T should be positive."""
        T = 25.0  # Above T_ref = 23.661
        y = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        H_V = vapor_enthalpy_numeric(T, y)
        # Should be positive (above ref + latent heat)
        assert H_V > 0

    def test_liquid_enthalpy_near_zero_at_ref(self):
        """Liquid enthalpy at T_ref should be ~0."""
        from h2iso.mesh.enthalpy import T_REF

        x = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
        H_L = liquid_enthalpy_numeric(T_REF, x)
        assert abs(H_L) < 1.0  # Should be ~0 at reference

    def test_vapor_gt_liquid(self):
        """At same T, vapor enthalpy > liquid enthalpy (latent heat)."""
        T = 24.0
        comp = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])
        H_V = vapor_enthalpy_numeric(T, comp)
        H_L = liquid_enthalpy_numeric(T, comp)
        assert H_V > H_L

    def test_sx_matches_numeric(self):
        """Symbolic and numeric enthalpy should give same result."""
        T_val = 24.0
        comp = np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0])

        # Numeric
        H_V_num = vapor_enthalpy_numeric(T_val, comp)
        H_L_num = liquid_enthalpy_numeric(T_val, comp)

        # Symbolic evaluation
        T_sx = ca.SX.sym("T")
        x_sx = ca.SX.sym("x", 6)
        H_V_sx = vapor_enthalpy_sx(T_sx, x_sx)
        H_L_sx = liquid_enthalpy_sx(T_sx, x_sx)

        f_V = ca.Function("hv", [T_sx, x_sx], [H_V_sx])
        f_L = ca.Function("hl", [T_sx, x_sx], [H_L_sx])

        H_V_ca = float(f_V(T_val, comp))
        H_L_ca = float(f_L(T_val, comp))

        assert abs(H_V_ca - H_V_num) < 1e-10
        assert abs(H_L_ca - H_L_num) < 1e-10
