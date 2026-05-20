"""Regression tests for the importlib.resources-based data loader."""

from __future__ import annotations

import json

import pytest

from h2iso._data import data_path

PARAMETER_FILES = [
    "species.json",
    "bip.json",
    "vapor_pressure.json",
    "quantum.json",
    "equilibrium.json",
    "enthalpy.json",
]


@pytest.mark.parametrize("filename", PARAMETER_FILES)
def test_parameter_file_loadable(filename: str) -> None:
    """Each bundled parameter file must resolve to a real path and parse as JSON."""
    with data_path("parameters", filename) as path:
        assert path.exists(), f"{filename} not found at {path}"
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data, f"{filename} parsed to empty dict"


def test_schema_file_loadable() -> None:
    """Bundled flowsheet schema must be reachable too."""
    with data_path("schemas", "flowsheet_v1.json") as path:
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)


def test_missing_file_raises() -> None:
    """Asking for a non-existent file must error out clearly (FileNotFoundError or OSError)."""
    with pytest.raises((FileNotFoundError, OSError)):
        with data_path("parameters", "does_not_exist.json") as path:
            open(path).read()
