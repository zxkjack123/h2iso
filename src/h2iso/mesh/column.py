"""N-stage distillation column NLP assembly and IPOPT solution.

Assembles N copies of the single-stage MESH equations into a complete
NLP (Nonlinear Programming) problem for CasADi/IPOPT.

Uses CMO (Constant Molar Overflow) assumption:
- L and V are fixed analytically from reflux ratio and feed condition
- Decision variables: T, x, y per stage only

Column configuration:
- Stage 1 = condenser (total condenser)
- Stage N = reboiler (partial)
- Feed enters at feed_stage (or multiple feeds via FeedSpec list)
- Specification: reflux ratio R and distillate-to-feed ratio D/F
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import casadi as ca
import numpy as np

from h2iso.mesh.enthalpy import (
    liquid_enthalpy_numeric,
    vapor_enthalpy_numeric,
)
from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.souers import pvap_sx


@dataclass
class FeedSpec:
    """Specification for a single feed stream."""

    stage: int  # 1-indexed from top
    flow: float  # mol/h
    composition: np.ndarray  # (6,)
    quality: float = 1.0  # q=1 saturated liquid


@dataclass
class ColumnSpec:
    """Column specification."""

    n_stages: int
    feed_stage: int  # 1-indexed from top (legacy single-feed)
    feed_flow: float  # mol/h (legacy single-feed)
    feed_composition: np.ndarray  # (6,) (legacy single-feed)
    pressure: float  # Pa (uniform for now)
    reflux_ratio: float
    distillate_to_feed: float  # D/F
    feed_quality: float = 1.0  # q=1 saturated liquid (legacy single-feed)
    feeds: list[FeedSpec] | None = None  # Multi-feed list (overrides legacy fields)


@dataclass
class ColumnResult:
    """Solution of the column NLP."""

    T_profile: np.ndarray  # (N,)
    x_profile: np.ndarray  # (N, 6)
    y_profile: np.ndarray  # (N, 6)
    L_profile: np.ndarray  # (N,)
    V_profile: np.ndarray  # (N,)
    condenser_duty: float  # W (negative = cooling)
    reboiler_duty: float  # W (positive = heating)
    convergence_info: dict = field(default_factory=dict)


class Column:
    """N-stage distillation column NLP builder and solver (CMO model)."""

    def __init__(self, spec: ColumnSpec):
        self.spec = spec
        self.N = spec.n_stages
        self.Nc = N_SPECIES

    def _get_feeds(self) -> list[FeedSpec]:
        """Get feed list (multi-feed or legacy single-feed)."""
        if self.spec.feeds is not None:
            return self.spec.feeds
        return [FeedSpec(
            stage=self.spec.feed_stage,
            flow=self.spec.feed_flow,
            composition=self.spec.feed_composition,
            quality=self.spec.feed_quality,
        )]

    def _total_feed_flow(self) -> float:
        """Total feed flow across all feeds."""
        return sum(f.flow for f in self._get_feeds())

    def _compute_flows(self) -> tuple[np.ndarray, np.ndarray]:
        """Compute L and V profiles under CMO assumption.

        Returns (L[N], V[N]) arrays.
        For multi-feed: each feed at stage j adds q_k*F_k to L and
        subtracts (1-q_k)*F_k from V below that stage.
        """
        spec = self.spec
        F_total = self._total_feed_flow()
        D = spec.distillate_to_feed * F_total
        R = spec.reflux_ratio
        feeds = self._get_feeds()

        L = np.zeros(self.N)
        V = np.zeros(self.N)

        # Base flows (rectifying section = above all feeds)
        L_base = R * D
        V_base = (R + 1) * D

        for j in range(self.N):
            L[j] = L_base
            V[j] = V_base
            # Add contribution from each feed at or above this stage
            for f in feeds:
                feed_j = f.stage - 1  # 0-indexed
                if j >= feed_j:
                    L[j] += f.quality * f.flow
                    V[j] -= (1 - f.quality) * f.flow

        # Special: V[0] = 0 for total condenser (no vapor leaves)
        V[0] = 0.0
        # L[N-1] represents B (bottoms product flow)
        B = F_total - D
        L[-1] = B

        return L, V

    def build_nlp(self) -> dict[str, Any]:
        """Build the CasADi NLP for IPOPT.

        Under CMO, decision variables are T_j, x_j(6), y_j(6) per stage = 13*N.
        """
        N = self.N
        Nc = self.Nc
        spec = self.spec
        P = spec.pressure
        feeds = self._get_feeds()
        F_total = self._total_feed_flow()
        D = spec.distillate_to_feed * F_total
        B = F_total - D

        # Build feed map: stage_index -> (flow, composition) for that feed
        feed_map: dict[int, list[tuple[float, np.ndarray]]] = {}
        for f in feeds:
            j = f.stage - 1  # 0-indexed
            feed_map.setdefault(j, []).append((f.flow, f.composition))

        L, V = self._compute_flows()

        # Decision variables per stage: T(1) + x(6) + y(6) = 13
        n_vars_per_stage = 1 + Nc + Nc  # 13

        w = []
        w0 = []
        lbw = []
        ubw = []
        g = []
        lbg = []
        ubg = []

        T_vars = []
        x_vars = []
        y_vars = []

        # Initial guess: use linear composition profile for better convergence
        # Top (distillate-like): enrich light key, bottom: deplete light key
        # Use flow-weighted average composition for multi-feed
        z_avg = np.zeros(Nc)
        for f in feeds:
            z_avg += f.flow * f.composition
        z_avg /= F_total

        x_top_init = z_avg.copy()
        x_bot_init = z_avg.copy()
        # Find dominant component and boost it at top
        i_light = int(np.argmax(z_avg))
        x_top_init[i_light] = min(0.99, z_avg[i_light] * 1.05)
        # Normalize
        x_top_init /= x_top_init.sum()
        # Bottom: reduce light key
        x_bot_init[i_light] = max(0.01, z_avg[i_light] * 0.5)
        x_bot_init /= x_bot_init.sum()

        # Linear T profile (increasing from top to bottom)
        T_init = np.linspace(23.5, 24.5, N)

        for j in range(N):
            frac = j / max(N - 1, 1)
            x_j_init = (1 - frac) * x_top_init + frac * x_bot_init

            # Temperature
            T_j = ca.SX.sym(f"T_{j}")
            T_vars.append(T_j)
            w.append(T_j)
            w0.append(T_init[j])
            lbw.append(14.0)
            ubw.append(35.0)

            # Liquid composition
            x_j = ca.SX.sym(f"x_{j}", Nc)
            x_vars.append(x_j)
            for i in range(Nc):
                w.append(x_j[i])
                w0.append(x_j_init[i])
                lbw.append(0.0)
                ubw.append(1.0)

            # Vapor composition
            y_j = ca.SX.sym(f"y_{j}", Nc)
            y_vars.append(y_j)
            for i in range(Nc):
                w.append(y_j[i])
                w0.append(x_j_init[i])
                lbw.append(0.0)
                ubw.append(1.0)

        # === Constraints ===

        for j in range(N):
            # --- Equilibrium ---
            if j == 0:
                # Total condenser: x_0 = y_0 (saturated liquid = vapor composition)
                for i in range(Nc):
                    g.append(x_vars[0][i] - y_vars[0][i])
                    lbg.append(0.0)
                    ubg.append(0.0)
            else:
                # VLE: y_j = K_j * x_j where K = Psat/P (modified Raoult)
                for i, sp in enumerate(SPECIES_ORDER):
                    Psat_i = pvap_sx(T_vars[j], sp)
                    K_i = Psat_i / P
                    g.append(y_vars[j][i] - K_i * x_vars[j][i])
                    lbg.append(0.0)
                    ubg.append(0.0)

            # --- Summation ---
            g.append(ca.sum1(x_vars[j]) - 1.0)
            lbg.append(0.0)
            ubg.append(0.0)

            if j == 0:
                # Bubble point equation: sum(K_i * x_0_i) = 1
                # This constrains T_0 (replaces redundant sum(y_0)=1)
                bp_sum = ca.SX(0)
                for i, sp in enumerate(SPECIES_ORDER):
                    Psat_i = pvap_sx(T_vars[0], sp)
                    bp_sum = bp_sum + (Psat_i / P) * x_vars[0][i]
                g.append(bp_sum - 1.0)
                lbg.append(0.0)
                ubg.append(0.0)
            else:
                g.append(ca.sum1(y_vars[j]) - 1.0)
                lbg.append(0.0)
                ubg.append(0.0)

            # --- Material Balance (Nc-1 independent components) ---
            # Under CMO + summation, sum of all component MBs = 0, so one is redundant.
            # Drop last component (index Nc-1).
            for i in range(Nc - 1):
                if j == 0:
                    # Condenser: V[1]*y[1]_i = (L[0] + D)*x[0]_i
                    # Under CMO: V[1] = (R+1)*D, L[0] = R*D
                    # So: V[1]*y[1]_i - (R+1)*D*x[0]_i = 0
                    mb = V[1] * y_vars[1][i] - (L[0] + D) * x_vars[0][i]
                elif j == N - 1:
                    # Reboiler: L[N-2]*x[N-2]_i - V[N-1]*y[N-1]_i - B*x[N-1]_i = 0
                    mb = L[j - 1] * x_vars[j - 1][i] - V[j] * y_vars[j][i] - B * x_vars[j][i]
                    # Add feed if reboiler is a feed stage
                    if j in feed_map:
                        for f_flow, f_z in feed_map[j]:
                            mb = mb + f_flow * f_z[i]
                else:
                    # Internal: L[j-1]*x[j-1] + V[j+1]*y[j+1] + F_j*z - L[j]*x[j] - V[j]*y[j] = 0
                    mb = (L[j - 1] * x_vars[j - 1][i]
                          + V[j + 1] * y_vars[j + 1][i]
                          - L[j] * x_vars[j][i]
                          - V[j] * y_vars[j][i])
                    # Add feed(s) at this stage
                    if j in feed_map:
                        for f_flow, f_z in feed_map[j]:
                            mb = mb + f_flow * f_z[i]

                g.append(mb)
                lbg.append(0.0)
                ubg.append(0.0)

        # Formulate NLP (feasibility: f=0)
        w_vec = ca.vertcat(*w)
        g_vec = ca.vertcat(*g)

        nlp = {"x": w_vec, "f": ca.SX(0), "g": g_vec}

        opts = {
            "ipopt.max_iter": 3000,
            "ipopt.tol": 1e-8,
            "ipopt.print_level": 0,
            "print_time": False,
            "ipopt.sb": "yes",
        }
        solver = ca.nlpsol("column", "ipopt", nlp, opts)

        return {
            "solver": solver,
            "x0": np.array(w0),
            "lbx": np.array(lbw),
            "ubx": np.array(ubw),
            "lbg": np.array(lbg),
            "ubg": np.array(ubg),
            "n_vars_per_stage": n_vars_per_stage,
        }

    def solve(self, x0: np.ndarray | None = None) -> ColumnResult:
        """Solve the column NLP.

        Parameters
        ----------
        x0 : ndarray, optional
            Initial guess vector. If None, uses default linear profile.

        Returns
        -------
        ColumnResult
        """
        nlp_data = self.build_nlp()
        solver = nlp_data["solver"]

        if x0 is None:
            x0 = nlp_data["x0"]

        sol = solver(
            x0=x0,
            lbx=nlp_data["lbx"],
            ubx=nlp_data["ubx"],
            lbg=nlp_data["lbg"],
            ubg=nlp_data["ubg"],
        )

        w_opt = np.array(sol["x"]).flatten()
        stats = solver.stats()

        return self._extract_result(w_opt, stats)

    def _extract_result(self, w_opt: np.ndarray, stats: dict) -> ColumnResult:
        """Extract profiles from flat solution vector."""
        N = self.N
        Nc = self.Nc
        n_per = 1 + Nc + Nc  # 13 vars per stage

        T_prof = np.zeros(N)
        x_prof = np.zeros((N, Nc))
        y_prof = np.zeros((N, Nc))

        for j in range(N):
            offset = j * n_per
            T_prof[j] = w_opt[offset]
            x_prof[j, :] = w_opt[offset + 1: offset + 1 + Nc]
            y_prof[j, :] = w_opt[offset + 1 + Nc: offset + 1 + 2 * Nc]

        L, V = self._compute_flows()

        # Compute heat duties from enthalpy differences
        x_top = x_prof[0]
        x_bot = x_prof[-1]

        H_V_top = vapor_enthalpy_numeric(T_prof[1], x_top)
        H_L_top = liquid_enthalpy_numeric(T_prof[0], x_top)
        Q_cond = -V[1] * (H_V_top - H_L_top) / 3600.0  # W

        H_L_bot = liquid_enthalpy_numeric(T_prof[-1], x_bot)
        H_V_bot = vapor_enthalpy_numeric(T_prof[-1], x_bot)
        Q_reb = V[-1] * (H_V_bot - H_L_bot) / 3600.0  # W

        return ColumnResult(
            T_profile=T_prof,
            x_profile=x_prof,
            y_profile=y_prof,
            L_profile=L,
            V_profile=V,
            condenser_duty=Q_cond,
            reboiler_duty=Q_reb,
            convergence_info={
                "status": stats.get("return_status", "unknown"),
                "iterations": stats.get("iter_count", -1),
                "success": stats.get("return_status") in (
                    "Solve_Succeeded",
                    "Solved_To_Acceptable_Level",
                    "Feasible_Point_Found",
                ),
            },
        )
