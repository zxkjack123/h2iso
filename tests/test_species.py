"""Tests for species registry."""

from h2iso import SPECIES, Species
from h2iso.species import N_SPECIES, SPECIES_ORDER, species_index


def test_species_count():
    assert len(SPECIES) == N_SPECIES == 6


def test_species_order():
    assert SPECIES_ORDER == ["H2", "HD", "HT", "D2", "DT", "T2"]


def test_molar_masses():
    """Molar masses should match IUPAC 2021 values."""
    expected = {
        "H2": 2.01588,
        "HD": 3.02204,
        "HT": 4.02399,
        "D2": 4.02820,
        "DT": 5.03015,
        "T2": 6.03210,
    }
    for formula, mass in expected.items():
        assert abs(SPECIES[formula].molar_mass - mass) < 1e-5, (
            f"{formula}: expected {mass}, got {SPECIES[formula].molar_mass}"
        )


def test_molar_mass_ordering():
    """Molar mass should increase: H2 < HD < HT ≈ D2 < DT < T2."""
    masses = [SPECIES[f].molar_mass for f in SPECIES_ORDER]
    for i in range(len(masses) - 1):
        assert masses[i] <= masses[i + 1]


def test_atom_conservation():
    """Each species should have exactly 2 atoms total."""
    for sp in SPECIES.values():
        assert sp.atom_count == 2, f"{sp.formula} has {sp.atom_count} atoms"


def test_species_index():
    assert species_index("H2") == 0
    assert species_index("T2") == 5
    assert species_index("DT") == 4


def test_species_is_frozen():
    """Species should be immutable."""
    sp = SPECIES["H2"]
    assert isinstance(sp, Species)
    try:
        sp.molar_mass = 999  # type: ignore
        assert False, "Should raise"
    except Exception:
        pass
