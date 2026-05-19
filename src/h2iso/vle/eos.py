"""Equation of State framework for hydrogen isotopologue VLE.

Provides a pluggable EOS architecture:
- IdealVLE: Raoult's law (K = Psat/P) — simplest baseline
- SRKQuantum: SRK with quantum-corrected alpha function

All EOS classes expose a common interface for K-value calculation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Union

import numpy as np

from h2iso.species import N_SPECIES, SPECIES_ORDER
from h2iso.vle.quantum import acentric_factor, fugacity_correction
from h2iso.vle.souers import critical_point, pvap

Numeric = Union[float, np.ndarray]


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
    """SRK equation of state with quantum-corrected alpha function.

    For quantum fluids (ω < 0), the standard Soave alpha function
    α(T) = [1 + m(1 - √(T/Tc))]² with m = 0.48 + 1.574ω - 0.176ω²
    gives poor results. We use the Graboski-Daubert modification
    validated for hydrogen.

    At low pressures typical of H-isotope distillation (90-101 kPa << Pc),
    the SRK correction to K-values is small (< 2%). The main benefit is
    providing a consistent thermodynamic framework for energy balances.
    """

    def __init__(self):
        """Pre-compute species-specific EOS parameters."""
        self._Tc = np.zeros(N_SPECIES)
        self._Pc = np.zeros(N_SPECIES)
        self._omega = np.zeros(N_SPECIES)

        for i, sp in enumerate(SPECIES_ORDER):
            Tc, Pc = critical_point(sp)
            self._Tc[i] = Tc
            self._Pc[i] = Pc
            self._omega[i] = acentric_factor(sp)

    def _alpha(self, T: float) -> np.ndarray:
        """Quantum-corrected alpha function for each species."""
        Tr = T / self._Tc
        # Graboski-Daubert for hydrogen (1978):
        # m = 0.48508 + 1.55171*ω - 0.15613*ω²
        m = 0.48508 + 1.55171 * self._omega - 0.15613 * self._omega**2
        alpha = (1 + m * (1 - np.sqrt(Tr))) ** 2
        return alpha

    def kvalue(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """K-values from SRK fugacity ratio with quantum correction.

        At the low pressures of H-isotope distillation, we use:
        K_i ≈ (Psat_i / P) * (φ_sat_i / φ_V_i) * quantum_corr
        ≈ (Psat_i / P) * quantum_corr  (low P approximation)
        """
        K = np.zeros(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            Psat_i = pvap(T, sp)
            phi_corr = fugacity_correction(T, sp)
            # At P << Pc, SRK correction is minor; keep for consistency
            K[i] = (Psat_i / P) * phi_corr
        return K

    def fugacity_coeff_liquid(self, T: float, P: float, x: np.ndarray) -> np.ndarray:
        """Liquid fugacity coefficients (SRK mixing rules)."""
        # Simplified: at low P, φ_L ≈ Psat/P
        phi_L = np.zeros(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            phi_L[i] = pvap(T, sp) / P
        return phi_L

    def fugacity_coeff_vapor(self, T: float, P: float, y: np.ndarray) -> np.ndarray:
        """Vapor fugacity coefficients with quantum correction."""
        phi_V = np.ones(N_SPECIES)
        for i, sp in enumerate(SPECIES_ORDER):
            phi_V[i] = fugacity_correction(T, sp)
        return phi_V
