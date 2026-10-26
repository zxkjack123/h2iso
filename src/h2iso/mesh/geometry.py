"""Physical geometry of a real distillation column.

This module defines :class:`ColumnGeometry`, the vessel/column hardware
description that h2iso's solver needs in order to

* convert real geometry into equivalent theoretical stages
  (:mod:`h2iso.mesh.performance`),
* compute per-stage liquid/vapour holdup and tritium inventory
  (:mod:`h2iso.mesh.holdup`).

The class deliberately covers both column families used in the ISS
(Isotope Separation System):

* **packed** columns (structured or random packing), and
* **tray** columns (sieve / bubble-cap / valve trays),

with the end volumes (condenser, reboiler) shared between both.

All quantities are SI (m, m^2, m^3, K, Pa).  ``None`` means "not known /
not applicable"; :meth:`ColumnGeometry.validate` checks that the fields
required by :attr:`column_type` are present.

References for the parameter names follow standard distillation practice
(Kister, *Distillation Design*, 1992; Stichlmair & Fair, *Distillation:
Principles and Practice*, 1998).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ColumnType = Literal["theoretical", "packed", "tray"]
TrayType = Literal["sieve", "bubble-cap", "valve"]


@dataclass
class ColumnGeometry:
    """Vessel geometry of a distillation column (SI units).

    Parameters
    ----------
    column_type : {"theoretical", "packed", "tray"}
        ``"theoretical"`` is geometry-free (the historical h2iso mode).
    diameter_m : float, optional
        Inside column diameter ``D`` [m].  Required for holdup computation
        of ``packed`` and ``tray`` columns.
    packing_height_m : float, optional
        Total packed height ``H_packing`` [m] (packed columns).
    packing_type : str, optional
        Free-form packing label, e.g. ``"B7"``, ``"Sulzer CY"``,
        ``"Raschig ring 6 mm"``.  Used for the HETP reference database.
    packing_specific_area_m2_m3 : float, optional
        Packing specific surface area ``a_p`` [m^2/m^3] (packed columns).
    packing_void_fraction : float, optional
        Packing void fraction ``eps`` [-] (packed columns).
    tray_count : int, optional
        Number of actual trays ``N_actual`` (tray columns; does *not*
        include condenser/reboiler).
    tray_spacing_m : float, optional
        Tray spacing ``H_t`` [m] (tray columns).
    tray_type : {"sieve", "bubble-cap", "valve"}, optional
        Tray type (tray columns).
    weir_height_m : float, optional
        Outlet weir height ``h_w`` [m] (tray columns).
    weir_length_m : float, optional
        Weir length ``W`` [m]; if not given it is estimated from the
        column diameter (see :mod:`h2iso.mesh.holdup`).
    hole_area_m2 : float, optional
        Total hole/riser area per tray [m^2].
    hole_diameter_m : float, optional
        Hole diameter [m] (sieve trays).
    condenser_volume_m3 : float, optional
        Condenser drum volume [m^3].
    reboiler_volume_m3 : float, optional
        Reboiler (kettle) volume [m^3].
    """

    column_type: ColumnType = "theoretical"

    diameter_m: float | None = None

    # --- packed section ---
    packing_height_m: float | None = None
    packing_type: str | None = None
    packing_specific_area_m2_m3: float | None = None
    packing_void_fraction: float | None = None
    hetp_m: float | None = None

    # --- tray section ---
    tray_count: int | None = None
    tray_spacing_m: float | None = None
    tray_type: TrayType | None = None
    weir_height_m: float | None = None
    weir_length_m: float | None = None
    hole_area_m2: float | None = None
    hole_diameter_m: float | None = None
    hole_pitch_m: float | None = None  # hole centre-to-centre distance
    downcomer_area_fraction: float | None = None  # A_d / A_T per downcomer side

    # --- end volumes ---
    condenser_volume_m3: float | None = None
    reboiler_volume_m3: float | None = None

    # ------------------------------------------------------------------
    # validation / helpers
    # ------------------------------------------------------------------

    def validate(self, for_holdup: bool = False) -> None:
        """Raise ``ValueError`` if the geometry is internally inconsistent.

        Parameters
        ----------
        for_holdup : bool
            When ``True``, additionally require the fields that the
            holdup correlations need (diameter, packing/weir details).
        """
        if self.column_type == "packed":
            if self.packing_height_m is not None and self.packing_height_m <= 0:
                raise ValueError("packing_height_m must be > 0")
            if self.hetp_m is not None and self.hetp_m <= 0:
                raise ValueError("hetp_m must be > 0")
            if (
                self.packing_void_fraction is not None
                and not 0.0 < self.packing_void_fraction < 1.0
            ):
                raise ValueError("packing_void_fraction must lie in (0, 1)")
            if (
                self.packing_specific_area_m2_m3 is not None
                and self.packing_specific_area_m2_m3 <= 0
            ):
                raise ValueError("packing_specific_area_m2_m3 must be > 0")
            if for_holdup:
                missing = [
                    name
                    for name in (
                        "diameter_m",
                        "packing_height_m",
                        "packing_specific_area_m2_m3",
                        "packing_void_fraction",
                    )
                    if getattr(self, name) is None
                ]
                if missing:
                    raise ValueError(
                        "packed-column holdup requires: " + ", ".join(missing)
                    )
        elif self.column_type == "tray":
            if self.tray_count is not None and self.tray_count < 1:
                raise ValueError("tray_count must be >= 1")
            if self.tray_spacing_m is not None and self.tray_spacing_m <= 0:
                raise ValueError("tray_spacing_m must be > 0")
            if self.weir_height_m is not None and self.weir_height_m <= 0:
                raise ValueError("weir_height_m must be > 0")
            if self.hole_pitch_m is not None and self.hole_pitch_m <= 0:
                raise ValueError("hole_pitch_m must be > 0")
            if (
                self.hole_pitch_m is not None
                and self.hole_diameter_m is not None
                and self.hole_pitch_m <= self.hole_diameter_m
            ):
                raise ValueError("hole_pitch_m must be larger than hole_diameter_m")
            if self.downcomer_area_fraction is not None and not (
                0.0 < self.downcomer_area_fraction < 0.3
            ):
                raise ValueError("downcomer_area_fraction must lie in (0, 0.3)")
            if for_holdup:
                missing = [
                    name
                    for name in (
                        "diameter_m",
                        "tray_spacing_m",
                        "tray_count",
                        "weir_height_m",
                    )
                    if getattr(self, name) is None
                ]
                if missing:
                    raise ValueError(
                        "tray-column holdup requires: " + ", ".join(missing)
                    )
        elif self.column_type != "theoretical":
            raise ValueError(
                f"column_type must be 'theoretical', 'packed' or 'tray'; "
                f"got {self.column_type!r}"
            )

        if self.diameter_m is not None and self.diameter_m <= 0:
            raise ValueError("diameter_m must be > 0")
        for name in ("condenser_volume_m3", "reboiler_volume_m3"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be > 0")

    @property
    def cross_section_area_m2(self) -> float:
        """Column cross-section area [m^2]; requires ``diameter_m``."""
        if self.diameter_m is None:
            raise ValueError("diameter_m is required to compute cross-section area")
        import math

        return math.pi * (self.diameter_m / 2.0) ** 2

    @property
    def active_tray_height_m(self) -> float | None:
        """Height spanned by the trays [m] (``tray_count * tray_spacing``)."""
        if self.tray_count is None or self.tray_spacing_m is None:
            return None
        return self.tray_count * self.tray_spacing_m

    def to_dict(self) -> dict:
        """Plain-dict form (JSON-serialisable; ``None`` fields kept)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ColumnGeometry:
        """Build from a plain dict, rejecting unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown ColumnGeometry fields: {sorted(unknown)}")
        return cls(**data)

    @classmethod
    def from_flowsheet_config(cls, cfg) -> ColumnGeometry:
        """Build from a :class:`h2iso.flowsheet.schema.ColumnConfig`.

        The flowsheet schema stores the fields that were already needed by
        the inventory module (``inside_diameter_m``, ``HETP_m``, condenser
        and reboiler volumes).  The result is a ``packed`` geometry with
        unknown packing internals, which is sufficient for HETP-based
        stage conversion but **not** for detailed holdup correlations.
        """
        return cls(
            column_type="packed",
            diameter_m=getattr(cfg, "inside_diameter_m", None),
            hetp_m=getattr(cfg, "HETP_m", None),
            packing_height_m=getattr(cfg, "packing_height_m", None),
            packing_type=getattr(cfg, "packing_type", None),
            condenser_volume_m3=getattr(cfg, "condenser_volume_m3", None),
            reboiler_volume_m3=getattr(cfg, "reboiler_volume_m3", None),
        )
