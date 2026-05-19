"""Tests for Modelica record and function code generation."""

from __future__ import annotations

import math
import re

import pytest

from h2iso.codegen.modelica_records import (
    generate_species_records,
    generate_vle_functions,
    pvap_reference,
)

SPECIES = ["H2", "HD", "HT", "D2", "DT", "T2"]
TEST_TEMPERATURES = [20.0, 24.0, 28.0]


class TestGenerateSpeciesRecords:
    """Test Modelica species record generation."""

    def test_generates_all_six_species(self):
        records = generate_species_records()
        assert len(records) == 6
        for sp in SPECIES:
            assert f"HydrogenIsotope_{sp}.mo" in records

    def test_record_syntax(self):
        """Each record should start with 'record' and end with 'end'."""
        records = generate_species_records()
        for sp in SPECIES:
            content = records[f"HydrogenIsotope_{sp}.mo"]
            assert content.startswith(f"record HydrogenIsotope_{sp}")
            assert content.strip().endswith(f"end HydrogenIsotope_{sp};")

    def test_contains_molar_mass(self):
        records = generate_species_records()
        for sp in SPECIES:
            content = records[f"HydrogenIsotope_{sp}.mo"]
            assert "MolarMass" in content
            # Should contain a numeric value
            assert re.search(r"M\s*=\s*[\d.]+e-3", content)

    def test_contains_critical_properties(self):
        records = generate_species_records()
        for sp in SPECIES:
            content = records[f"HydrogenIsotope_{sp}.mo"]
            assert "T_critical" in content
            assert "P_critical" in content
            assert "T_triple" in content

    def test_write_to_directory(self, tmp_path):
        records = generate_species_records(output_dir=tmp_path)
        for sp in SPECIES:
            fpath = tmp_path / f"HydrogenIsotope_{sp}.mo"
            assert fpath.exists()
            assert fpath.read_text() == records[f"HydrogenIsotope_{sp}.mo"]


class TestGenerateVleFunctions:
    """Test Modelica vapor pressure function generation."""

    def test_generates_all_six_functions(self):
        functions = generate_vle_functions()
        assert len(functions) == 6
        for sp in SPECIES:
            assert f"pvap_{sp}.mo" in functions

    def test_function_syntax(self):
        """Each function should start with 'function' and end with 'end'."""
        functions = generate_vle_functions()
        for sp in SPECIES:
            content = functions[f"pvap_{sp}.mo"]
            assert content.startswith(f"function pvap_{sp}")
            assert content.strip().endswith(f"end pvap_{sp};")

    def test_contains_correlation_constants(self):
        functions = generate_vle_functions()
        for sp in SPECIES:
            content = functions[f"pvap_{sp}.mo"]
            assert "C1" in content
            assert "C2" in content
            assert "C3" in content
            assert "C4" in content
            assert "C5" in content

    def test_contains_valid_range_annotation(self):
        functions = generate_vle_functions()
        for sp in SPECIES:
            content = functions[f"pvap_{sp}.mo"]
            assert "Valid range" in content

    def test_write_to_directory(self, tmp_path):
        functions = generate_vle_functions(output_dir=tmp_path)
        for sp in SPECIES:
            fpath = tmp_path / f"pvap_{sp}.mo"
            assert fpath.exists()
            assert fpath.read_text() == functions[f"pvap_{sp}.mo"]


class TestPvapConsistency:
    """Verify generated Modelica pvap values match Python reference.

    The acceptance criterion is < 0.01% deviation at T = 20, 24, 28 K.
    """

    @pytest.mark.parametrize("species", SPECIES)
    @pytest.mark.parametrize("T", TEST_TEMPERATURES)
    def test_pvap_matches_at_test_temperatures(self, species, T):
        """Generated function constants must reproduce Python values."""
        from h2iso.vle.souers import pvap

        # Reference from the existing numpy-based implementation
        P_numpy = pvap(T, species)

        # Reference from pure-Python implementation in codegen
        P_codegen = pvap_reference(T, species)

        # Both should agree to within floating point
        rel_err = abs(P_numpy - P_codegen) / P_numpy
        assert rel_err < 1e-10, (
            f"{species} at {T} K: numpy={P_numpy:.6e}, codegen={P_codegen:.6e}, "
            f"rel_err={rel_err:.2e}"
        )

    @pytest.mark.parametrize("species", SPECIES)
    @pytest.mark.parametrize("T", TEST_TEMPERATURES)
    def test_modelica_constants_reproduce_python(self, species, T):
        """Parse constants from generated .mo and evaluate — must match < 0.01%."""
        functions = generate_vle_functions()
        content = functions[f"pvap_{species}.mo"]

        # Extract constants from the generated Modelica code
        constants = {}
        for cname in ["C1", "C2", "C3", "C4", "C5"]:
            match = re.search(rf"{cname}\s*=\s*([-\d.eE+]+)", content)
            assert match, f"Could not find {cname} in pvap_{species}.mo"
            constants[cname] = float(match.group(1))

        # Evaluate the correlation
        ln_P = (
            constants["C1"]
            + constants["C2"] / T
            + constants["C3"] * math.log(T)
            + constants["C4"] * T ** constants["C5"]
        )
        P_modelica = math.exp(ln_P)

        # Compare to Python reference
        P_ref = pvap_reference(T, species)
        rel_err = abs(P_modelica - P_ref) / P_ref

        assert rel_err < 1e-4, (
            f"{species} at {T} K: modelica={P_modelica:.6e}, ref={P_ref:.6e}, "
            f"rel_err={rel_err:.2e} (threshold 0.01%)"
        )
