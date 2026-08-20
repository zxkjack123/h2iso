"""Data models and parameters for tritium inventory evaluation in distillation columns.

Based on the inventory formulation in:
    X. Wang et al., "Hydrogen isotope inventory evaluation of hydrogen isotopes
    separation system of CFETR using Aspen Plus simulator", Fusion Eng. Des. 184 (2022) 113078.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from h2iso.species import SPECIES_ORDER

# Gas constant [J/(mol·K)]
R_GAS = 8.314462618

# Liquid molar volumes [m^3/mol] at NBP from Wang 2022 Table 7
# (H2=2.924E-5, HD=2.635E-5, HT=2.526E-5, D2=2.415E-5, DT=2.326E-5, T2=2.245E-5)
DEFAULT_MOLAR_VOLUMES: dict[str, float] = {
    "H2": 2.924e-5,
    "HD": 2.635e-5,
    "HT": 2.526e-5,
    "D2": 2.415e-5,
    "DT": 2.326e-5,
    "T2": 2.245e-5,
}

# Tritium equivalence factor alpha_i (moles equivalent T2 per mole of species)
# (H2=0, HD=0, HT=0.5, D2=0, DT=0.5, T2=1.0)
DEFAULT_TRITIUM_EQUIVALENCE: dict[str, float] = {
    "H2": 0.0,
    "HD": 0.0,
    "HT": 0.5,
    "D2": 0.0,
    "DT": 0.5,
    "T2": 1.0,
}

# Grams of tritium per mole of T2 molecule (2 * 3.01605 = 6.0321 g/mol T2)
TRITIUM_MOLAR_MASS_T2_G_PER_MOL = 6.0321


@dataclass
class InventoryGeometry:
    """Geometric and volumetric parameters for column inventory calculation."""

    inside_diameter_m: float = 0.05
    HETP_m: float = 0.05
    condenser_volume_m3: float = 1.0e-3
    reboiler_volume_m3: float = 2.0e-4
    eps_condenser: float = 0.01   # epsilon_1: liquid ratio against condenser volume (1%)
    eps_stage: float = 0.10       # epsilon_j: liquid ratio against stage volume (10%)
    eps_reboiler: float = 0.05    # epsilon_N: liquid ratio against reboiler volume (5%)
    eps_packing: float = 0.20     # epsilon: ratio of packing volume (20%)


@dataclass
class ColumnInventoryResult:
    """Tritium inventory breakdown for a single distillation column."""

    column_name: str
    gas_condenser_mol: float     # H_VC
    gas_packed_mol: float        # H_VP
    gas_reboiler_mol: float      # H_VR
    liquid_condenser_mol: float  # H_LC
    liquid_packed_mol: float     # H_LP
    liquid_reboiler_mol: float   # H_LR
    
    stage_gas_inventory_mol: np.ndarray = field(default_factory=lambda: np.zeros(0))
    stage_liquid_inventory_mol: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def total_gas_mol(self) -> float:
        """Total gas-phase tritium inventory in moles of equivalent T2."""
        return self.gas_condenser_mol + self.gas_packed_mol + self.gas_reboiler_mol

    @property
    def total_liquid_mol(self) -> float:
        """Total liquid-phase tritium inventory in moles of equivalent T2."""
        return self.liquid_condenser_mol + self.liquid_packed_mol + self.liquid_reboiler_mol

    @property
    def total_mol(self) -> float:
        """Total tritium inventory in moles of equivalent T2."""
        return self.total_gas_mol + self.total_liquid_mol

    @property
    def total_grams(self) -> float:
        """Total tritium inventory in grams of tritium."""
        return self.total_mol * TRITIUM_MOLAR_MASS_T2_G_PER_MOL

    def to_dict(self) -> dict:
        """Convert inventory breakdown to dictionary."""
        return {
            "column_name": self.column_name,
            "total_mol": float(self.total_mol),
            "total_grams": float(self.total_grams),
            "gas_phase_mol": {
                "condenser": float(self.gas_condenser_mol),
                "packed_section": float(self.gas_packed_mol),
                "reboiler": float(self.gas_reboiler_mol),
                "total": float(self.total_gas_mol),
            },
            "liquid_phase_mol": {
                "condenser": float(self.liquid_condenser_mol),
                "packed_section": float(self.liquid_packed_mol),
                "reboiler": float(self.liquid_reboiler_mol),
                "total": float(self.total_liquid_mol),
            },
        }


@dataclass
class FlowsheetInventoryResult:
    """Tritium inventory evaluation across multiple columns in a flowsheet."""

    columns: dict[str, ColumnInventoryResult] = field(default_factory=dict)

    @property
    def total_mol(self) -> float:
        """Total tritium inventory across all columns in moles of equivalent T2."""
        return sum(c.total_mol for c in self.columns.values())

    @property
    def total_grams(self) -> float:
        """Total tritium inventory across all columns in grams of tritium."""
        return sum(c.total_grams for c in self.columns.values())

    @property
    def total_gas_mol(self) -> float:
        return sum(c.total_gas_mol for c in self.columns.values())

    @property
    def total_liquid_mol(self) -> float:
        return sum(c.total_liquid_mol for c in self.columns.values())

    def to_dict(self) -> dict:
        """Convert full flowsheet inventory to dictionary."""
        return {
            "total_mol": float(self.total_mol),
            "total_grams": float(self.total_grams),
            "total_gas_mol": float(self.total_gas_mol),
            "total_liquid_mol": float(self.total_liquid_mol),
            "columns": {k: v.to_dict() for k, v in self.columns.items()},
        }
