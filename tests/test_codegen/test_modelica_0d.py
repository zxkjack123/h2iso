"""Tests for Modelica 0-D surrogate code and override generation."""

from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

from h2iso.codegen.modelica_0d import (
    export_modelica_package,
    generate_column_override_lines,
    generate_generic_iss_mo,
    generate_iss_adapters_mo,
    generate_override_from_results,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "wang2022"


class TestGenericISSModelicaCode:
    """Test the generated Generic_ISS.mo library (Pure Wang 2022 Core)."""

    def test_package_structure(self):
        mo = generate_generic_iss_mo()
        assert "package Generic_ISS" in mo
        assert "end Generic_ISS;" in mo

    def test_contains_only_core_models(self):
        mo = generate_generic_iss_mo()
        expected_models = [
            "model Column_0D_6",
            "model Equilibrator_0D_6",
            "model ISS_I_Core",
            "model ISS_O_Core",
        ]
        for model in expected_models:
            assert model in mo, f"Missing {model} in Generic_ISS.mo"

        # Adapters should NOT be in Generic_ISS.mo
        assert "ISS_I_Adapter" not in mo
        assert "ISS_O_Adapter" not in mo

    def test_column_parameters_evaluate_false(self):
        mo = generate_generic_iss_mo()
        # Verify Evaluate=false annotations for override support
        assert "m_top_ref[6]" in mo
        assert "m_bottom_ref[6]" in mo
        assert "annotation(Evaluate=false)" in mo

    def test_equilibrator_chemistry_equations(self):
        mo = generate_generic_iss_mo()
        # Verify isotopic exchange stoichiometry in Equilibrator
        assert "2.0 * a_H * a_D" in mo
        assert "2.0 * a_H * a_T" in mo
        assert "2.0 * a_D * a_T" in mo


class TestGenericISSAdaptersCode:
    """Test the generated Generic_ISS_Adapters.mo library (Multi-Component Adapters)."""

    def test_package_structure(self):
        mo = generate_iss_adapters_mo()
        assert "package Generic_ISS_Adapters" in mo
        assert "end Generic_ISS_Adapters;" in mo

    def test_contains_adapter_models(self):
        mo = generate_iss_adapters_mo()
        assert "model ISS_I_Adapter" in mo
        assert "model ISS_O_Adapter" in mo
        assert "Generic_ISS.ISS_I_Core core;" in mo
        assert "Generic_ISS.ISS_O_Core core;" in mo

    def test_mass_weighting_factors(self):
        mo = generate_iss_adapters_mo()
        assert "MW_T/MW[3]" in mo
        assert "MW_D/MW[2]" in mo
        assert "MW_H/MW[2]" in mo


class TestOverrideGeneration:
    """Test generating override.txt from Wang 2022 result JSON files."""

    @pytest.fixture
    def issi_results(self):
        with open(FIXTURES_DIR / "wang2022_issi_results.json", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def isso_results(self):
        with open(FIXTURES_DIR / "wang2022_isso_results.json", encoding="utf-8") as f:
            return json.load(f)

    def test_issi_override_generation(self, issi_results):
        txt = generate_override_from_results(issi_results)
        for col in ["CD1", "CD2", "CD3", "CD4"]:
            assert f"{col}.T_top=" in txt
            assert f"{col}.T_bottom=" in txt
            assert f"{col}.tau=" in txt
            for i in range(1, 7):
                assert f"{col}.m_top_ref[{i}]=" in txt
                assert f"{col}.m_bottom_ref[{i}]=" in txt

        # Check CD1 temperatures are within reasonable range
        assert re.search(r"CD1\.T_top=23\.\d+", txt)
        assert re.search(r"CD1\.T_bottom=24\.\d+", txt)

    def test_isso_override_generation(self, isso_results):
        txt = generate_override_from_results(isso_results)
        for col in ["CD1", "CD2", "CD3"]:
            assert f"{col}.T_top=" in txt
            assert f"{col}.T_bottom=" in txt
            assert f"{col}.tau=" in txt
            for i in range(1, 7):
                assert f"{col}.m_top_ref[{i}]=" in txt
                assert f"{col}.m_bottom_ref[{i}]=" in txt

        # Check CD1 temperatures
        assert re.search(r"CD1\.T_top=20\.\d+", txt)
        assert re.search(r"CD1\.T_bottom=22\.\d+", txt)

    def test_tau_and_masses_are_positive_and_finite(self, issi_results):
        txt = generate_override_from_results(issi_results)
        for line in txt.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("//"):
                key, val = line.split("=", 1)
                val_float = float(val)
                assert not (val_float != val_float)  # not NaN
                assert abs(val_float) < 1e10
                if "tau" in key:
                    assert val_float > 0, f"{key} tau must be positive"


class TestExportModelicaPackage:
    """Test full package export functionality."""

    def test_export_to_directory(self, tmp_path):
        paths = export_modelica_package(tmp_path)
        assert "Generic_ISS.mo" in paths
        assert "Generic_ISS_Adapters.mo" in paths
        assert (tmp_path / "Generic_ISS.mo").exists()
        assert (tmp_path / "Generic_ISS_Adapters.mo").exists()

        if (FIXTURES_DIR / "wang2022_issi_results.json").exists():
            assert "override_issi.txt" in paths
            assert (tmp_path / "override_issi.txt").exists()
            assert (tmp_path / "override_isso.txt").exists()
