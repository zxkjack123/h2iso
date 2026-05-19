"""Profile export utilities for column results.

Supports CSV, JSON, and MAT (MATLAB v4) output formats.
"""

from __future__ import annotations

import json
from pathlib import Path

from h2iso.mesh.column import ColumnResult
from h2iso.species import SPECIES_ORDER


def export_csv(result: ColumnResult, path: str | Path) -> None:
    """Export column profiles to CSV.

    Columns: stage, T, x_H2, x_HD, x_HT, x_D2, x_DT, x_T2,
             y_H2, y_HD, y_HT, y_D2, y_DT, y_T2, L, V
    """
    path = Path(path)
    N = len(result.T_profile)

    header = ["stage", "T"]
    header.extend([f"x_{sp}" for sp in SPECIES_ORDER])
    header.extend([f"y_{sp}" for sp in SPECIES_ORDER])
    header.extend(["L", "V"])

    with open(path, "w") as f:
        f.write(",".join(header) + "\n")
        for j in range(N):
            row = [str(j + 1), f"{result.T_profile[j]:.10g}"]
            row.extend([f"{result.x_profile[j, i]:.10g}" for i in range(6)])
            row.extend([f"{result.y_profile[j, i]:.10g}" for i in range(6)])
            row.extend([f"{result.L_profile[j]:.10g}", f"{result.V_profile[j]:.10g}"])
            f.write(",".join(row) + "\n")


def export_json(result: ColumnResult, path: str | Path) -> None:
    """Export column profiles to structured JSON with metadata."""
    path = Path(path)
    N = len(result.T_profile)

    data = {
        "format": "h2iso_column_result",
        "version": "1.0",
        "n_stages": N,
        "species": list(SPECIES_ORDER),
        "profiles": {
            "T": result.T_profile.tolist(),
            "x": result.x_profile.tolist(),
            "y": result.y_profile.tolist(),
            "L": result.L_profile.tolist(),
            "V": result.V_profile.tolist(),
        },
        "heat_duties": {
            "condenser_W": result.condenser_duty,
            "reboiler_W": result.reboiler_duty,
        },
        "convergence": result.convergence_info,
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def export_mat(result: ColumnResult, path: str | Path) -> None:
    """Export column profiles to MAT v4 file (OpenModelica readMatrix compatible).

    Matrix layout:
    - T_profile: (N, 1)
    - x_profile: (N, 6)
    - y_profile: (N, 6)
    - L_profile: (N, 1)
    - V_profile: (N, 1)
    """
    from scipy.io import savemat

    path = Path(path)

    mdict = {
        "T_profile": result.T_profile.reshape(-1, 1),
        "x_profile": result.x_profile,
        "y_profile": result.y_profile,
        "L_profile": result.L_profile.reshape(-1, 1),
        "V_profile": result.V_profile.reshape(-1, 1),
    }

    savemat(str(path), mdict, do_compression=False, format="4")
