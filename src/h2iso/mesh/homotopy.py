"""Homotopy solver for transitioning between model fidelity levels.

Currently wraps the CMO column solver directly (since CMO IS the
simplified model). Future: implements homotopy from CMO → full energy
balance model.
"""

from __future__ import annotations

from h2iso.mesh.column import Column, ColumnResult, ColumnSpec


def homotopy_solve(
    spec: ColumnSpec,
    lambda_steps: int = 1,
) -> ColumnResult:
    """Solve column using homotopy from simplified to full model.

    Currently uses CMO (the simplified model) directly since no
    full energy balance model exists yet. The lambda_steps parameter
    is reserved for future use when transitioning CMO → rigorous MESH.

    Parameters
    ----------
    spec : ColumnSpec
        Column specification.
    lambda_steps : int
        Number of homotopy steps (reserved for future use).

    Returns
    -------
    ColumnResult
    """
    # Currently: CMO IS the simplified model, solve directly
    col = Column(spec)
    return col.solve()
