"""Tests for profile export (Task 2.4).

Tests:
1. CSV export readable with correct columns
2. JSON export with schema validation
3. MAT export readable by scipy.io.loadmat
4. Round-trip numerical fidelity < 1e-10
5. Modelica .mos script generation
"""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest
from scipy.io import loadmat

pytest.importorskip("casadi")

from h2iso.codegen.modelica_init import generate_init_script
from h2iso.mesh.column import Column, ColumnSpec
from h2iso.mesh.export import export_csv, export_json, export_mat
from h2iso.species import SPECIES_ORDER


@pytest.fixture
def column_result():
    """Solve a small column for export testing."""
    feed = np.zeros(6)
    feed[3] = 0.90
    feed[4] = 0.07
    feed[5] = 0.03
    spec = ColumnSpec(
        n_stages=10,
        feed_stage=5,
        feed_flow=100.0,
        feed_composition=feed,
        pressure=101325.0,
        reflux_ratio=5.0,
        distillate_to_feed=0.90,
    )
    col = Column(spec)
    result = col.solve()
    assert result.convergence_info["success"]
    return result


class TestCSVExport:
    """Test CSV export."""

    def test_csv_creates_file(self, column_result, tmp_path):
        path = tmp_path / "profile.csv"
        export_csv(column_result, path)
        assert path.exists()

    def test_csv_columns(self, column_result, tmp_path):
        path = tmp_path / "profile.csv"
        export_csv(column_result, path)

        with open(path) as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header[0] == "stage"
        assert header[1] == "T"
        assert "x_D2" in header
        assert "y_T2" in header
        assert "L" in header
        assert "V" in header
        assert len(header) == 16  # stage + T + 6x + 6y + L + V

    def test_csv_row_count(self, column_result, tmp_path):
        path = tmp_path / "profile.csv"
        export_csv(column_result, path)

        with open(path) as f:
            lines = f.readlines()
        # Header + N data rows
        assert len(lines) == 1 + len(column_result.T_profile)

    def test_csv_roundtrip_fidelity(self, column_result, tmp_path):
        path = tmp_path / "profile.csv"
        export_csv(column_result, path)

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for j, row in enumerate(rows):
            T_read = float(row["T"])
            np.testing.assert_allclose(T_read, column_result.T_profile[j], rtol=1e-9)


class TestJSONExport:
    """Test JSON export."""

    def test_json_creates_file(self, column_result, tmp_path):
        path = tmp_path / "profile.json"
        export_json(column_result, path)
        assert path.exists()

    def test_json_schema(self, column_result, tmp_path):
        path = tmp_path / "profile.json"
        export_json(column_result, path)

        with open(path) as f:
            data = json.load(f)

        assert data["format"] == "h2iso_column_result"
        assert data["version"] == "1.0"
        assert data["n_stages"] == len(column_result.T_profile)
        assert data["species"] == list(SPECIES_ORDER)
        assert "profiles" in data
        assert "T" in data["profiles"]
        assert "x" in data["profiles"]
        assert "heat_duties" in data

    def test_json_roundtrip_fidelity(self, column_result, tmp_path):
        path = tmp_path / "profile.json"
        export_json(column_result, path)

        with open(path) as f:
            data = json.load(f)

        T_read = np.array(data["profiles"]["T"])
        np.testing.assert_allclose(T_read, column_result.T_profile, rtol=1e-14)

        x_read = np.array(data["profiles"]["x"])
        np.testing.assert_allclose(x_read, column_result.x_profile, rtol=1e-14)


class TestMATExport:
    """Test MAT export."""

    def test_mat_creates_file(self, column_result, tmp_path):
        path = tmp_path / "profile.mat"
        export_mat(column_result, path)
        assert path.exists()

    def test_mat_loadable(self, column_result, tmp_path):
        path = tmp_path / "profile.mat"
        export_mat(column_result, path)

        mdict = loadmat(str(path))
        assert "T_profile" in mdict
        assert "x_profile" in mdict
        assert "y_profile" in mdict
        assert "L_profile" in mdict
        assert "V_profile" in mdict

    def test_mat_roundtrip_fidelity(self, column_result, tmp_path):
        path = tmp_path / "profile.mat"
        export_mat(column_result, path)

        mdict = loadmat(str(path))
        T_read = mdict["T_profile"].flatten()
        np.testing.assert_allclose(T_read, column_result.T_profile, rtol=1e-14)

        x_read = mdict["x_profile"]
        np.testing.assert_allclose(x_read, column_result.x_profile, rtol=1e-14)

    def test_mat_shape(self, column_result, tmp_path):
        path = tmp_path / "profile.mat"
        export_mat(column_result, path)

        mdict = loadmat(str(path))
        N = len(column_result.T_profile)
        assert mdict["T_profile"].shape == (N, 1)
        assert mdict["x_profile"].shape == (N, 6)


class TestModelicaInit:
    """Test Modelica .mos script generation."""

    def test_generates_script(self, column_result):
        script = generate_init_script(column_result, "Tricys.CD2")
        assert "Tricys.CD2" in script
        assert "T_init" in script
        assert "x_D2_init" in script
        assert "y_T2_init" in script
        assert "Q_cond" in script
        assert "Q_reb" in script

    def test_script_has_correct_n_stages(self, column_result):
        script = generate_init_script(column_result, "Tricys.CD2")
        N = len(column_result.T_profile)
        assert f"N_stages = {N}" in script

    def test_script_contains_all_species(self, column_result):
        script = generate_init_script(column_result, "Tricys.CD2")
        for sp in SPECIES_ORDER:
            assert f"x_{sp}_init" in script
            assert f"y_{sp}_init" in script
