"""Equation of State framework for hydrogen isotopologue VLE.

Provides a pluggable EOS architecture:
- IdealVLE: Raoult's law (K = Psat/P) — simplest baseline
- SRKQuantum: full SRK cubic EOS with vdW mixing and quantum-corrected alpha

All EOS classes expose a common interface for K-value calculation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Union

import numpy as np

from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.quantum import (
    acentric_factor,
    fugacity_correction,
    quantum_alpha_correction,
)
from h2iso.vle.souers import critical_point, pvap

Numeric = Union[float, np.ndarray]

# Universal gas constant (J/(mol·K))
_R_GAS = 8.314462618


class EOS(ABC):
    """Abstract base class for equations of state."""

    @abstractmethod
    def kvalue(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """Compute K-values (y_i/x_i) for all species.

        Parameters
        ----------
        T : float
            Temperature in K.
        P : float
            Pressure in Pa.
        x : ndarray of shape (6,)
            Liquid mole fractions.

        Returns
        -------
        ndarray of shape (6,)
            K-values for each species.
        """

    @abstractmethod
    def fugacity_coeff_liquid(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """Liquid-phase fugacity coefficients."""

    @abstractmethod
    def fugacity_coeff_vapor(self, T: float, P: float, y: np.ndarray) -> np.ndarray:
        """Vapor-phase fugacity coefficients."""


class IdealVLE(EOS):
    """Ideal VLE: modified Raoult's law with quantum correction.

    K_i = (Psat_i / P) * quantum_correction_i

    This is the simplest model, suitable for:
    - Initial estimates and warm-starting
    - Low-pressure systems (P << Pc)
    - Pedagogical use
    """

    def kvalue(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """K-values via modified Raoult's law."""
        K = np.zeros(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            Psat_i = pvap(T, sp)
            phi_corr = fugacity_correction(T, sp)
            K[i] = (Psat_i / P) * phi_corr
        return K

    def fugacity_coeff_liquid(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """Ideal liquid: φ_L = Psat/P (Poynting neglected at low P)."""
        phi_L = np.zeros(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            phi_L[i] = pvap(T, sp) / P
        return phi_L

    def fugacity_coeff_vapor(self, T: float, P: float, y: np.ndarray) -> np.ndarray:
        """Ideal vapor: φ_V = 1 (with quantum correction)."""
        phi_V = np.ones(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            phi_V[i] = fugacity_correction(T, sp)
        return phi_V


class SRKQuantum(EOS):
    """Soave-Redlich-Kwong EOS with quantum-corrected alpha for H-isotopologues.

    Cubic EOS:
        P = RT/(v-b) - a(T)/(v(v+b))

    For each species:
        a_i = 0.42748 R²Tc²/Pc · α_i(T)
        b_i = 0.08664 R Tc/Pc
        α_i(T) = α_classical · α_quantum

    Classical (Graboski-Daubert for quantum fluids):
        α_classical = [1 + m(1 - √(T/Tc))]²,  m = 0.48508 + 1.55171ω - 0.15613ω²

    Quantum (Feynman-Hibbs leading-order):
        α_quantum = quantum_alpha_correction(T, species)

    Mixing (van der Waals, k_ij = 0):
        a_mix = ΣΣ z_i z_j √(a_i a_j),  b_mix = Σ z_i b_i

    Cubic in Z = Pv/RT:
        Z³ - Z² + (A - B - B²)Z - AB = 0,  A = aP/(RT)², B = bP/RT

    Fugacity coefficient (SRK departure):
        ln φ_i = (Z-1) B_i/B - ln(Z-B) - (A/B)(2 Σ z_j √(a_i a_j)/a - B_i/B) ln(1 + B/Z)

    K_i = φ_L_i / φ_V_i.

    At P ≪ Pc (typical H-isotope distillation, ~100 kPa vs Pc ~1.3 MPa),
    SRK K-values approach the modified-Raoult limit within ~1%. At elevated
    pressure (>500 kPa) non-ideal behaviour becomes significant.
    """

    def __init__(self):
        self._Tc = np.zeros(N_SPECIES)
        self._Pc = np.zeros(N_SPECIES)
        self._omega = np.zeros(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            Tc, Pc = critical_point(sp)
            self._Tc[i] = Tc
            self._Pc[i] = Pc
            self._omega[i] = acentric_factor(sp)
        self._a_c = 0.42748 * (_R_GAS * self._Tc) ** 2 / self._Pc
        self._b = 0.08664 * _R_GAS * self._Tc / self._Pc

    def _alpha(self, T: float) -> np.ndarray:
        Tr = T / self._Tc
        m = 0.48508 + 1.55171 * self._omega - 0.15613 * self._omega**2
        alpha_classical = (1.0 + m * (1.0 - np.sqrt(Tr))) ** 2
        alpha_quantum = np.array(
            [quantum_alpha_correction(T, sp) for sp in SPECIES_ORDER]
        )
        return alpha_classical * alpha_quantum

    def _a_i(self, T: float) -> np.ndarray:
        return self._a_c * self._alpha(T)

    def _mix_a_b(
        self, T: float, z: np.ndarray
    ) -> tuple[float, float, np.ndarray, np.ndarray]:
        """Return (a_mix, b_mix, a_i vector, cross-sum Σ_j z_j √(a_i a_j))."""
        a_i = self._a_i(T)
        sqrt_a = np.sqrt(a_i)
        # cross[i] = Σ_j z_j √(a_i a_j) = √(a_i) · Σ_j z_j √(a_j)
        s = float(np.dot(z, sqrt_a))
        cross = sqrt_a * s
        a_mix = float(s * s)
        b_mix = float(np.dot(z, self._b))
        return a_mix, b_mix, a_i, cross

    @staticmethod
    def _cubic_roots(A: float, B: float) -> np.ndarray:
        """Real roots of Z³ - Z² + (A-B-B²)Z - AB = 0 with Z > B."""
        coeffs = [1.0, -1.0, A - B - B**2, -A * B]
        roots = np.roots(coeffs)
        real = roots[np.abs(roots.imag) < 1e-9].real
        real = real[real > B + 1e-12]
        if real.size == 0:
            # Degenerate: fall back to Z=1 (ideal gas) — caller will hit low-A,B regime
            return np.array([1.0])
        return real

    def _ln_phi(self, T: float, P: float, z: np.ndarray, phase: str) -> np.ndarray:
        """ln φ_i for a single phase ('L' or 'V')."""
        a_mix, b_mix, a_i, cross = self._mix_a_b(T, z)
        A = a_mix * P / (_R_GAS * T) ** 2
        B = b_mix * P / (_R_GAS * T)
        roots = self._cubic_roots(A, B)
        if phase == "L":
            Z = float(np.min(roots))
        elif phase == "V":
            Z = float(np.max(roots))
        else:
            raise ValueError(f"phase must be 'L' or 'V'; got {phase!r}")
        Bi = self._b * P / (_R_GAS * T)
        # Guard for the log argument
        ZmB = max(Z - B, 1e-300)
        log_term = np.log(1.0 + B / Z) if (Z > 0 and B / Z > -1.0) else 0.0
        ln_phi = (
            (Z - 1.0) * Bi / B
            - np.log(ZmB)
            - (A / B) * (2.0 * cross / a_mix - Bi / B) * log_term
        )
        return ln_phi

    def fugacity_coeff_liquid(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        return np.exp(self._ln_phi(T, P, x, "L"))

    def fugacity_coeff_vapor(self, T: float, P: float, y: np.ndarray) -> np.ndarray:
        phi_V = np.exp(self._ln_phi(T, P, y, "V"))
        # Apply Feynman-Hibbs gas-phase quantum correction multiplicatively
        for i, sp in enumerate(SPECIES_ORDER):
            phi_V[i] *= fugacity_correction(T, sp)
        return phi_V

    def kvalue(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """K-values anchored to Souers Psat with SRK vapour-phase residual.

        Uses the γ-φ formulation in the low-pressure limit:
            K_i = (Psat_i / P) · phi_corr_i / φ_V_i^{mix}(T, P, y)

        At P ≪ Pc the SRK vapour fugacity coefficient φ_V → 1 and the result
        reduces to modified Raoult (IdealVLE). At elevated P, φ_V departs
        from unity and produces the non-ideal correction. Liquid is treated
        as ideal solution (γ_i ≈ 1) and the Poynting correction is omitted
        (negligible at the operating pressures of H-isotope distillation).
        """
        # Initial Raoult K and y
        K = np.zeros(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            Psat_i = pvap(T, sp)
            phi_corr = fugacity_correction(T, sp)
            K[i] = (Psat_i / P) * phi_corr
        y = K * x
        ys = y.sum()
        y = y / ys if ys > 0 else np.full(N_SPECIES, 1.0 / N_SPECIES)
        # Successive substitution on φ_V
        for _ in range(25):
            phi_V = self.fugacity_coeff_vapor(T, P, y)
            K_new = np.zeros(N_SPECIES)
            for i, sp in enumerate(SPECIES_ORDER):
                Psat_i = pvap(T, sp)
                phi_corr = fugacity_correction(T, sp)
                # phi_corr already in phi_V (vapor); avoid double-counting:
                # K = (Psat/P) / φ_V^{SRK_residual}
                phi_V_residual = phi_V[i] / phi_corr  # strip out fugacity_correction
                K_new[i] = (Psat_i / P) / phi_V_residual
            y_new = K_new * x
            ys = y_new.sum()
            if ys > 0:
                y_new = y_new / ys
            if np.max(np.abs(K_new - K)) < 1e-9:
                K = K_new
                break
            K = K_new
            y = y_new
        return K
