"""Hydrogen isotope species registry.

Defines the 6 molecular hydrogen isotopologues with their physical constants.
All molar masses from IUPAC 2021 atomic weights.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "parameters"


@dataclass(frozen=True)
class Species:
    """A hydrogen isotopologue species."""

    name: str
    formula: str
    molar_mass: float  # g/mol
    atoms: dict[str, int]  # e.g. {"H": 2} or {"H": 1, "D": 1}

    @property
    def atom_count(self) -> int:
        return sum(self.atoms.values())


def _load_species() -> dict[str, Species]:
    """Load species registry from JSON parameter file."""
    path = _DATA_DIR / "species.json"
    with open(path) as f:
        data = json.load(f)

    registry = {}
    for entry in data["species"]:
        sp = Species(
            name=entry["name"],
            formula=entry["formula"],
            molar_mass=entry["molar_mass"],
            atoms=entry["atoms"],
        )
        registry[sp.formula] = sp
    return registry


SPECIES: dict[str, Species] = _load_species()

# Convenience list for iteration in canonical order
SPECIES_ORDER = ["H2", "HD", "HT", "D2", "DT", "T2"]

# Number of species
N_SPECIES = 6


def species_index(formula: str) -> int:
    """Return the canonical index (0-5) of a species by formula."""
    return SPECIES_ORDER.index(formula)
