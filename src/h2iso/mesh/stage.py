"""Single-stage MESH (Material-Equilibrium-Summation-Heat) equations.

Builds CasADi SX symbolic expressions for a single theoretical plate
in a cryogenic hydrogen isotope distillation column.

The MESH equations for stage j with N_c = 6 components are:
- 6 Material balance equations: L_{j-1}*x_{j-1,i} + V_{j+1}*y_{j+1,i}
  + F_j*z_{j,i} - L_j*x_{j,i} - V_j*y_{j,i} = 0
- 6 Equilibrium equations: y_{j,i} - K_{j,i} * x_{j,i} = 0
- 2 Summation equations: Σ x_i = 1, Σ y_i = 1
- 1 Energy balance: L_{j-1}*H_L_{j-1} + V_{j+1}*H_V_{j+1}
  + F_j*H_F_j - L_j*H_L_j - V_j*H_V_j - Q_j = 0

Total: 15 equations per stage, 15 unknowns (6 x_i + 6 y_i + T + L + V).
"""

from __future__ import annotations

import casadi as ca

from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.souers import pvap_sx


class Stage:
    """Single theoretical plate equation builder using CasADi SX."""

    N_C = N_SPECIES  # 6 components
    N_EQ = 2 * N_SPECIES + 2 + 1  # 15 equations per stage

    def __init__(self, pressure: float = 90000.0):
        """Initialize with operating pressure.

        Parameters
        ----------
        pressure : float
            Stage pressure in Pa.
        """
        self.P = pressure

    @staticmethod
    def material_balance(
        L_in: ca.SX,
        x_in: ca.SX,
        V_in: ca.SX,
        y_in: ca.SX,
        L_out: ca.SX,
        x_out: ca.SX,
        V_out: ca.SX,
        y_out: ca.SX,
        F: ca.SX,
        z: ca.SX,
    ) -> ca.SX:
        """Material balance for all components.

        L_in*x_in + V_in*y_in + F*z - L_out*x_out - V_out*y_out = 0

        Returns
        -------
        casadi.SX of shape (6, 1)
            Residual vector.
        """
        residual = L_in * x_in + V_in * y_in + F * z - L_out * x_out - V_out * y_out
        return residual

    @staticmethod
    def equilibrium(T_sx: ca.SX, P: float, x: ca.SX, y: ca.SX) -> ca.SX:
        """Phase equilibrium equations: y_i - K_i(T,P) * x_i = 0.

        K-values computed from Souers pvap correlation in symbolic mode.

        Returns
        -------
        casadi.SX of shape (6, 1)
            Residual vector.
        """
        residuals = []
        for i, sp in enumerate(SPECIES_ORDER):
            # K_i = Psat_i(T) / P (modified Raoult's law)
            Psat_i = pvap_sx(T_sx, sp)
            K_i = Psat_i / P
            residuals.append(y[i] - K_i * x[i])
        return ca.vertcat(*residuals)

    @staticmethod
    def summation(x: ca.SX, y: ca.SX) -> ca.SX:
        """Summation equations: Σx = 1, Σy = 1.

        Returns
        -------
        casadi.SX of shape (2, 1)
            Residual vector [sum_x - 1, sum_y - 1].
        """
        sum_x = ca.sum1(x) - 1.0
        sum_y = ca.sum1(y) - 1.0
        return ca.vertcat(sum_x, sum_y)

    @staticmethod
    def energy_balance(
        L_in: ca.SX,
        H_L_in: ca.SX,
        V_in: ca.SX,
        H_V_in: ca.SX,
        L_out: ca.SX,
        H_L_out: ca.SX,
        V_out: ca.SX,
        H_V_out: ca.SX,
        F: ca.SX,
        H_F: ca.SX,
        Q: ca.SX,
    ) -> ca.SX:
        """Energy balance equation.

        L_in*H_L_in + V_in*H_V_in + F*H_F - L_out*H_L_out - V_out*H_V_out - Q = 0

        Returns
        -------
        casadi.SX (scalar)
            Energy residual.
        """
        return (
            L_in * H_L_in
            + V_in * H_V_in
            + F * H_F
            - L_out * H_L_out
            - V_out * H_V_out
            - Q
        )

    def build_residual(
        self,
        T: ca.SX,
        x: ca.SX,
        y: ca.SX,
        L_in: ca.SX,
        L_out: ca.SX,
        V_in: ca.SX,
        V_out: ca.SX,
        x_in: ca.SX,
        y_in: ca.SX,
        F: ca.SX,
        z: ca.SX,
        Q: ca.SX,
        H_L_in: ca.SX,
        H_V_in: ca.SX,
        H_L_out: ca.SX,
        H_V_out: ca.SX,
        H_F: ca.SX,
    ) -> ca.SX:
        """Build the full 15-equation residual vector.

        Returns
        -------
        casadi.SX of shape (15, 1)
            Full MESH residual.
        """
        # Material (6 eq)
        M = self.material_balance(L_in, x_in, V_in, y_in, L_out, x, V_out, y, F, z)
        # Equilibrium (6 eq)
        E = self.equilibrium(T, self.P, x, y)
        # Summation (2 eq)
        S = self.summation(x, y)
        # Energy/Heat (1 eq)
        H = self.energy_balance(
            L_in, H_L_in, V_in, H_V_in, L_out, H_L_out, V_out, H_V_out, F, H_F, Q
        )

        return ca.vertcat(M, E, S, H)
