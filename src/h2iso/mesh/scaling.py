"""Variable scaling for MESH NLP.

Scaling strategy for hydrogen isotope distillation:
- Temperature: T_scaled = T / T_ref where T_ref = 25 K
- Mole fractions: x, y ∈ [0, 1] (no scaling needed)
- Pressure: P_scaled = P / 1e5
- Flows: L, V scaled by feed flow
"""

from __future__ import annotations


class ColumnScaling:
    """Variable scaling and bounds for column NLP."""

    def __init__(self, n_stages: int, T_ref: float = 25.0, F_ref: float = 100.0):
        self.n_stages = n_stages
        self.T_ref = T_ref
        self.F_ref = F_ref

    def scale_T(self, T: float) -> float:
        return T / self.T_ref

    def unscale_T(self, T_s: float) -> float:
        return T_s * self.T_ref

    def scale_flow(self, flow: float) -> float:
        return flow / self.F_ref

    def unscale_flow(self, flow_s: float) -> float:
        return flow_s * self.F_ref

    def get_bounds(self) -> dict:
        """Return bounds for all variable types."""
        return {
            "T": (14.0 / self.T_ref, 35.0 / self.T_ref),  # 14-35 K
            "x": (0.0, 1.0),
            "y": (0.0, 1.0),
            "L": (0.0, 100.0),  # Scaled by F_ref
            "V": (0.0, 100.0),
        }
