"""Column performance specification and geometry -> theoretical stage conversion.

h2iso's MESH solver works in **theoretical stages** (``ColumnSpec.n_stages``).
Real engineering users, however, specify packed height + HETP, or actual tray
count + overall/Murphree efficiency.  This module is the conversion layer
between the two worlds.

Stage convention (matches :mod:`h2iso.mesh.column`)
---------------------------------------------------
Stage 1 = condenser, stage N = reboiler, i.e. ``ColumnSpec.n_stages``
**includes** the two end stages.  Conversions from hardware geometry add the
two end stages when ``include_end_stages=True`` (default), so the result can
be fed directly into ``ColumnSpec.n_stages``.

Supported modes
---------------
``"theoretical_stages"``
    Expert mode: ``n_stages`` is given directly (historical behaviour).
``"hetp"``
    Packed columns: ``N_ideal = ceil(H_packing / HETP)``; the HETP value is
    taken from :class:`ColumnPerformance` or from the geometry/HETP database.
``"tray_efficiency"``
    Tray columns: ``N_ideal = ceil(E_overall * N_actual_trays)``.

The resulting stage counts are *engineering conversions*, not calibrations:
the theoretical-stage model still assumes ideal equilibrium stages; the
converted ``N`` merely reflects how much separation the real hardware can
deliver.  The HETP reference values shipped with this module are
literature-transcribed engineering priors: they carry their source, validity
range and uncertainty, but they have **not** been independently re-verified
inside this repository (see ``src/h2iso/data/parameters/hetp_reference.json``,
``_integration_note``).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

from h2iso._data import data_path
from h2iso.mesh.geometry import ColumnGeometry

PerformanceMode = Literal["theoretical_stages", "hetp", "tray_efficiency"]


@dataclass
class ColumnPerformance:
    """How a real column's separation performance is specified.

    Exactly one of the modes is active; fields for the inactive modes are
    ignored (but kept so that a full specification can be stored in JSON).

    Parameters
    ----------
    mode : {"theoretical_stages", "hetp", "tray_efficiency"}
    n_theoretical : int, optional
        Required for ``"theoretical_stages"`` mode; may also serve as an
        explicitly stated override that is echoed back by
        :func:`resolve_theoretical_stages`.
    hetp_m : float, optional
        Height equivalent to a theoretical plate [m] (``"hetp"`` mode).
        If ``None``, the HETP is looked up in the HETP reference database
        by packing label, or taken from ``geometry`` if present.
    effective_height_m : float, optional
        Packed height actually used for the conversion [m].  Defaults to
        ``geometry.packing_height_m``.  Kept explicit so that margins
        (e.g. excluded redistribution sections) can be represented.
    overall_efficiency : float, optional
        Column (overall) efficiency ``E_overall`` in ``(0, 1]`` for
        ``"tray_efficiency"`` mode.  Note this is a *section/overall*
        efficiency, not a per-tray Murphree efficiency.
    """

    mode: PerformanceMode = "theoretical_stages"
    n_theoretical: int | None = None
    hetp_m: float | None = None
    effective_height_m: float | None = None
    overall_efficiency: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("theoretical_stages", "hetp", "tray_efficiency"):
            raise ValueError(
                "mode must be 'theoretical_stages', 'hetp' or 'tray_efficiency'; "
                f"got {self.mode!r}"
            )
        if self.hetp_m is not None and self.hetp_m <= 0:
            raise ValueError("hetp_m must be > 0")
        if self.effective_height_m is not None and self.effective_height_m <= 0:
            raise ValueError("effective_height_m must be > 0")
        if self.overall_efficiency is not None and not (
            0.0 < self.overall_efficiency <= 1.0
        ):
            raise ValueError("overall_efficiency must lie in (0, 1]")
        if self.n_theoretical is not None and self.n_theoretical < 1:
            raise ValueError("n_theoretical must be >= 1")


# ----------------------------------------------------------------------
# HETP reference database
# ----------------------------------------------------------------------

_HETP_DB: dict | None = None


def load_hetp_database() -> dict:
    """Load the HETP / overall-efficiency reference database (JSON).

    The database is an *engineering prior* collection: each value carries its
    source, validity range and uncertainty.  It is not a physical constant
    table.  See ``src/h2iso/data/parameters/hetp_reference.json``.
    """
    global _HETP_DB
    if _HETP_DB is None:
        with data_path("parameters", "hetp_reference.json") as path:
            with open(path, encoding="utf-8") as f:
                _HETP_DB = json.load(f)
    return _HETP_DB


def lookup_hetp(packing_type: str) -> dict | None:
    """Look up an HETP entry by packing label.

    Returns the entry dict (``{"hetp_m": ..., "uncertainty": ...,
    "source": ..., ...}``) or ``None`` when the packing is not in the
    database.  Matching is case-insensitive and ignores surrounding
    whitespace.
    """
    db = load_hetp_database()
    key = packing_type.strip().lower()
    for entry in db.get("packings", []):
        names = [entry.get("name", "")] + list(entry.get("aliases", []))
        if any(n.strip().lower() == key for n in names if n):
            return entry
    return None


# ----------------------------------------------------------------------
# conversion
# ----------------------------------------------------------------------


def resolve_theoretical_stages(
    geometry: ColumnGeometry | None = None,
    performance: ColumnPerformance | None = None,
    include_end_stages: bool = True,
) -> int:
    """Convert real column hardware into an equivalent theoretical stage count.

    Parameters
    ----------
    geometry : ColumnGeometry, optional
        Hardware description; provides heights, tray counts, tray spacing and
        (optionally) an HETP value.
    performance : ColumnPerformance, optional
        Performance specification selecting the mode.  ``None`` means
        ``"theoretical_stages"`` with no explicit count, which is an error.
    include_end_stages : bool
        When ``True`` (default) the condenser and reboiler are added to the
        converted contact-stage count, matching h2iso's ``n_stages``
        convention (stage 1 = condenser, stage N = reboiler).

    Returns
    -------
    int
        Equivalent ``ColumnSpec.n_stages``.

    Raises
    ------
    ValueError
        If the inputs do not provide the quantities required by the mode.
    """
    if performance is None:
        performance = ColumnPerformance(mode="theoretical_stages")
    if geometry is not None:
        geometry.validate()

    mode = performance.mode

    if mode == "theoretical_stages":
        if performance.n_theoretical is None:
            raise ValueError(
                "'theoretical_stages' mode requires n_theoretical "
                "(or pass the stage count directly to ColumnSpec.n_stages)"
            )
        return int(performance.n_theoretical)

    if mode == "hetp":
        hetp = performance.hetp_m
        source = "performance.hetp_m"
        if hetp is None and geometry is not None and geometry.hetp_m is not None:
            hetp = geometry.hetp_m
            source = "geometry.hetp_m"
        if hetp is None and geometry is not None and geometry.packing_type:
            entry = lookup_hetp(geometry.packing_type)
            if entry is not None:
                hetp = float(entry["hetp_m"])
                source = f"HETP database ({entry.get('source', 'n/a')})"
        if hetp is None or hetp <= 0:
            raise ValueError(
                "'hetp' mode requires hetp_m (on performance or geometry), or a "
                "packing_type present in the HETP database"
            )
        height = performance.effective_height_m
        if height is None and geometry is not None:
            height = geometry.packing_height_m
        if height is None or height <= 0:
            raise ValueError(
                "'hetp' mode requires effective_height_m or geometry.packing_height_m"
            )
        n_contact = int(math.ceil(height / hetp))
        if n_contact < 1:
            n_contact = 1
        _ = source  # kept for future diagnostics/logging
        return n_contact + (2 if include_end_stages else 0)

    # mode == "tray_efficiency"
    if geometry is None or geometry.tray_count is None:
        raise ValueError(
            "'tray_efficiency' mode requires geometry.tray_count "
            "(actual number of trays)"
        )
    if performance.overall_efficiency is None:
        raise ValueError("'tray_efficiency' mode requires overall_efficiency in (0, 1]")
    n_contact = int(math.ceil(performance.overall_efficiency * geometry.tray_count))
    if n_contact < 1:
        n_contact = 1
    return n_contact + (2 if include_end_stages else 0)


def equivalent_hetp(
    geometry: ColumnGeometry,
    performance: ColumnPerformance | None = None,
) -> float:
    """Equivalent HETP of a tray column [m] (engineering conversion).

    ``HETP_equiv = H_active / N_ideal_trays`` where ``H_active`` is the
    tray stack height and ``N_ideal_trays`` the overall-efficiency-corrected
    tray count (without end stages).  This is a *reporting* quantity, not a
    claim that the tray column behaves like packing.
    """
    if geometry.tray_count is None or geometry.tray_spacing_m is None:
        raise ValueError("equivalent_hetp requires tray_count and tray_spacing_m")
    e_overall = 1.0
    if performance is not None and performance.overall_efficiency is not None:
        e_overall = performance.overall_efficiency
    n_ideal = max(1, int(math.ceil(e_overall * geometry.tray_count)))
    h_active = geometry.tray_count * geometry.tray_spacing_m
    return h_active / n_ideal
