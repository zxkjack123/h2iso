"""Shared test fixtures for h2iso."""

import pytest


@pytest.fixture
def wang2022_cd2_feed():
    """Wang 2022 ISS-I CD2 feed condition."""
    return {
        "total_flow_mol_h": 80.357,
        "composition": {
            "H2": 0.0,
            "HD": 0.0,
            "D2": 0.98,
            "HT": 0.0,
            "DT": 0.02,
            "T2": 0.0,
        },
        "temperature_K": 25.0,
        "pressure_Pa": 90000,
    }
