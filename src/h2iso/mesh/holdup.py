"""Per-stage liquid / vapour holdup from column hydraulics (holdup/efficiency extension).

This module implements holdup correlations for the two column families used
in the ISS (Isotope Separation System):

**Tray columns** (sieve / bubble-cap)

* Bennett, Agrawal & Cook (1983) -- effective clear-liquid height, SI form
  as circulating in Perry's Handbook Sec. 14 / Wang et al. (2018, FRI).
* Hofhuis & Zuiderweg (1979) -- clear-liquid height from the flow group
  ``psi``; also applicable in the spray regime (Dhulesia's froth-regime
  variant is provided as well).

**Packed columns** (structured / random packing)

* Stichlmair, Bravo & Fair (1989) -- pre-loading and loading-region liquid
  holdup (formula cross-confirmed by six independent documents, including
  an executable MATLAB listing; no published worked example exists).
* Billet & Schultes -- liquid holdup for random and structured packings
  (implemented as the recommended substitute for "Bravo & Fair (1982)",
  which -- contrary to the declared demonstration basis -- is a **mass-transfer**
  paper and contains no holdup correlation; see the cited design note sec. 4).
* Rocha, Bravo & Fair (1993) -- structured-packing hydraulic model
  (``include_eps_in_denom`` switch documents the published definitional
  dispute between Qiu's comment and the authors' rebuttal; no published
  worked example exists -- cross-checked against the executable UFRJ
  MATLAB listing instead).

Unit conventions
----------------
All inputs and outputs are SI: metres, m^3, m^3/s, kg/m^3, mol, mol/h.
Volumetric flows here are **per column cross section carrier volume**;
molar flows are converted by the caller.

Verification
------------
Both tray correlations are validated against published worked examples in
``tests/test_mesh/test_holdup.py``:

* Bennett-Agrawal: Perry's 7th ed., Sec. 14, Example 11 (Method B) --
  reproduced to < 0.1%.
* Hofhuis-Zuiderweg: Zarzycki & Chacuk, *Absorption*, Example 12-A --
  reproduced to < 0.1%.

Cryogenic-service caveat
------------------------
These correlations were developed on air/water and hydrocarbon systems.
In liquid-hydrogen service ``rho_L - rho_V`` is comparatively small, which
pushes the Bennett-Agrawal froth-density factor ``phi_e`` toward its
lower limit; a clamp with a warning is applied and the validity of the
correlations for hydrogen isotopes at 20 K is an assumption to be stated
explicitly in the cited design note (no cryogenic-specific holdup
correlation exists in the open literature -- see the report).
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field

import numpy as np

from h2iso.mesh.geometry import ColumnGeometry

# Engineering defaults for tray internals when not given explicitly.
_G = 9.81  # gravitational acceleration [m/s^2]
_DEFAULT_DOWNCOMER_AREA_FRACTION = 0.10  # A_d / A_T per downcomer side
_DEFAULT_WEIR_LENGTH_TO_DIAMETER = 0.7
_PHI_E_FLOOR = 0.05  # numerical/validity floor for the froth density


@dataclass
class TrayHydraulics:
    """Result of a tray liquid-holdup correlation (SI units)."""

    h_clear_liquid_m: float  # clear-liquid height on the tray
    liquid_volume_m3: float  # liquid holdup (clear liquid) per tray
    active_area_m2: float
    froth_height_m: float | None = None
    phi_e: float | None = None  # effective froth density (Bennett-Agrawal)
    extras: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# tray helpers
# ----------------------------------------------------------------------


def tray_active_area(geometry: ColumnGeometry) -> float:
    """Tray active (bubbling) area ``A_active = A_T - 2 * A_d`` [m^2]."""
    if geometry.diameter_m is None:
        raise ValueError("diameter_m is required to compute the tray active area")
    a_t = geometry.cross_section_area_m2
    if geometry.downcomer_area_fraction is not None:
        frac = geometry.downcomer_area_fraction
    else:
        frac = _DEFAULT_DOWNCOMER_AREA_FRACTION
    return a_t * (1.0 - 2.0 * frac)


def tray_weir_length(geometry: ColumnGeometry) -> float:
    """Outlet weir length ``W`` [m]; defaults to ``0.7 * D`` when unknown."""
    if geometry.weir_length_m is not None:
        return geometry.weir_length_m
    if geometry.diameter_m is None:
        raise ValueError("diameter_m is required to estimate the weir length")
    return _DEFAULT_WEIR_LENGTH_TO_DIAMETER * geometry.diameter_m


# ----------------------------------------------------------------------
# Bennett / Agrawal / Cook (1983)
# ----------------------------------------------------------------------


def clear_liquid_height_bennett_agrawal(
    u_active: float,
    q_liquid_per_weir: float,
    h_w: float,
    rho_l: float,
    rho_v: float,
) -> tuple[float, dict]:
    """Bennett-Agrawal clear-liquid height from primitive quantities.

    Parameters
    ----------
    u_active : float
        Vapour velocity based on the active (bubbling) area [m/s].
    q_liquid_per_weir : float
        Liquid volumetric flow per unit weir length ``Q_L / W`` [m^2/s].
    h_w : float
        Outlet weir height [m].
    rho_l, rho_v : float
        Liquid and vapour densities [kg/m^3].

    Returns
    -------
    (h_L, info) : (float, dict)
        Clear-liquid height [m] and intermediate quantities
        (``K_s``, ``phi_e``, ``C``).

    Notes
    -----
    SI form (Wang et al. 2018, Eq. 5-6):

        K_s   = u_a * sqrt(rho_v / (rho_l - rho_v))
        phi_e = exp(-12.55 * K_s**0.91)
        C     = 0.5 + 0.438 * exp(-137.8 * h_w)
        h_L   = phi_e * (h_w + C * (q_liquid_per_weir / phi_e)**0.67)

    Equivalent to the Perry (mm) form
    ``h_L[mm] = phi_e (h_w[mm] + 15330 C_P (q/phi_e)^(2/3))`` with
    ``C_P = 0.0327 + 0.0286 exp(-0.1378 h_w[mm])`` (ratio 1000:15.33).
    """
    if rho_l <= rho_v:
        raise ValueError(
            f"liquid density must exceed vapour density; got rho_l={rho_l}, "
            f"rho_v={rho_v}"
        )
    if u_active < 0 or q_liquid_per_weir < 0:
        raise ValueError("flows must be non-negative")
    if h_w <= 0:
        raise ValueError(f"weir height must be > 0; got {h_w}")

    k_s = u_active * math.sqrt(rho_v / (rho_l - rho_v))
    phi_e = math.exp(-12.55 * k_s**0.91)
    if phi_e < _PHI_E_FLOOR:
        warnings.warn(
            f"Bennett-Agrawal froth density phi_e={phi_e:.4f} below the "
            f"correlation validity floor {_PHI_E_FLOOR}; clamping. "
            "(Low rho_l - rho_v -- typical for cryogenic hydrogen service.)",
            UserWarning,
            stacklevel=2,
        )
        phi_e = _PHI_E_FLOOR
    c_weir = 0.5 + 0.438 * math.exp(-137.8 * h_w)
    h_l = phi_e * (h_w + c_weir * (q_liquid_per_weir / phi_e) ** 0.67)

    return h_l, {"K_s": k_s, "phi_e": phi_e, "C": c_weir}


def liquid_holdup_tray_bennett_agrawal(
    geometry: ColumnGeometry,
    q_liquid_m3_s: float,
    q_vapor_m3_s: float,
    rho_l: float,
    rho_v: float,
) -> TrayHydraulics:
    """Per-tray liquid holdup, Bennett-Agrawal (1983)."""
    active = tray_active_area(geometry)
    if geometry.weir_height_m is None:
        raise ValueError("weir_height_m is required for the Bennett-Agrawal model")
    weir = tray_weir_length(geometry)

    u_active = q_vapor_m3_s / active
    q_per_weir = q_liquid_m3_s / weir
    h_l, info = clear_liquid_height_bennett_agrawal(
        u_active, q_per_weir, geometry.weir_height_m, rho_l, rho_v
    )
    return TrayHydraulics(
        h_clear_liquid_m=h_l,
        liquid_volume_m3=active * h_l,
        active_area_m2=active,
        froth_height_m=h_l / info["phi_e"],
        phi_e=info["phi_e"],
        extras={"K_s": info["K_s"], "C": info["C"]},
    )


# ----------------------------------------------------------------------
# Hofhuis / Zuiderweg (1979)
# ----------------------------------------------------------------------


def clear_liquid_height_hofhuis_zuiderweg(
    psi: float,
    h_w: float,
    hole_pitch: float,
    mode: str = "original",
) -> float:
    """Hofhuis-Zuiderweg clear-liquid height from the flow group ``psi``.

    Parameters
    ----------
    psi : float
        Flow group ``psi = (Q_L / W) / u_s * sqrt(rho_l / rho_g)`` [m],
        where ``u_s`` is the vapour velocity based on the bubbling area.
    h_w : float
        Weir height [m]; correlation range ``0.025 <= h_w <= 0.1``.
    hole_pitch : float
        Hole centre-to-centre distance [m] (**not** hole diameter).
    mode : {"original", "dhulesia_froth"}
        ``"original"``: ``h_cl = 0.6 psi^0.25 h_w^0.5 p^0.25`` (1979).
        ``"dhulesia_froth"``: ``h_cl = 0.5 psi^0.33 h_w^0.5 p^0.17``
        (Dhulesia 1984, froth regime, reported +/-10% vs experiments).

    Returns
    -------
    float
        Clear-liquid height [m].
    """
    if psi <= 0:
        raise ValueError(f"psi must be > 0; got {psi}")
    if hole_pitch <= 0:
        raise ValueError(f"hole_pitch must be > 0; got {hole_pitch}")
    if not (0.025 <= h_w <= 0.1):
        warnings.warn(
            f"weir height {h_w} m outside the Hofhuis-Zuiderweg validity "
            "range 0.025-0.1 m; result is an extrapolation",
            UserWarning,
            stacklevel=2,
        )
    if mode == "original":
        return 0.6 * psi**0.25 * h_w**0.5 * hole_pitch**0.25
    if mode == "dhulesia_froth":
        return 0.5 * psi**0.33 * h_w**0.5 * hole_pitch**0.17
    raise ValueError(f"mode must be 'original' or 'dhulesia_froth'; got {mode!r}")


def liquid_holdup_tray_hofhuis_zuiderweg(
    geometry: ColumnGeometry,
    q_liquid_m3_s: float,
    q_vapor_m3_s: float,
    rho_l: float,
    rho_v: float,
    *,
    hole_pitch_m: float | None = None,
    mode: str = "original",
) -> TrayHydraulics:
    """Per-tray liquid holdup, Hofhuis-Zuiderweg (1979)."""
    active = tray_active_area(geometry)
    if geometry.weir_height_m is None:
        raise ValueError("weir_height_m is required for the Hofhuis-Zuiderweg model")
    pitch = hole_pitch_m or geometry.hole_pitch_m
    if pitch is None:
        raise ValueError(
            "hole_pitch_m is required for the Hofhuis-Zuiderweg model "
            "(hole centre-to-centre distance)"
        )
    weir = tray_weir_length(geometry)

    u_s = q_vapor_m3_s / active
    if u_s <= 0:
        raise ValueError("vapor flow must be > 0 for the flow group psi")
    psi = (q_liquid_m3_s / weir) / u_s * math.sqrt(rho_l / rho_v)
    h_cl = clear_liquid_height_hofhuis_zuiderweg(
        psi, geometry.weir_height_m, pitch, mode=mode
    )
    return TrayHydraulics(
        h_clear_liquid_m=h_cl,
        liquid_volume_m3=active * h_cl,
        active_area_m2=active,
        extras={"psi": psi, "mode": mode},
    )


# ----------------------------------------------------------------------
# vapour holdup on trays
# ----------------------------------------------------------------------


def vapor_holdup_tray(
    geometry: ColumnGeometry,
    h_froth_m: float,
    active_area_m2: float | None = None,
) -> float:
    """Vapour holdup volume per tray [m^3].

    The vapour occupies the tray spacing minus the froth layer:
    ``V_V = A_active * (H_t - h_froth)``.  When the froth fills the
    spacing the result is clipped at zero with a warning (flooding).
    """
    if geometry.tray_spacing_m is None:
        raise ValueError("tray_spacing_m is required for vapour holdup")
    active = (
        active_area_m2 if active_area_m2 is not None else tray_active_area(geometry)
    )
    clear_height = geometry.tray_spacing_m - h_froth_m
    if clear_height <= 0:
        warnings.warn(
            f"froth height {h_froth_m:.4f} m fills the tray spacing "
            f"{geometry.tray_spacing_m:.4f} m (flooding); vapour holdup set to 0",
            UserWarning,
            stacklevel=2,
        )
        clear_height = 0.0
    return active * clear_height


# ----------------------------------------------------------------------
# packed columns -- Stichlmair, Bravo & Fair (1989)
# ----------------------------------------------------------------------


def liquid_holdup_packed_stichlmair(
    u_l: float,
    a_p: float,
    eps: float,
    *,
    dP_irr_per_Z: float | None = None,
    Z: float | None = None,
    rho_l: float | None = None,
    mu_l: float | None = None,
) -> dict:
    """Stichlmair-Bravo-Fair (1989) liquid holdup for packed columns.

    Parameters
    ----------
    u_l : float
        Superficial liquid velocity (based on the empty column cross
        section) [m/s].
    a_p : float
        Packing specific surface area [m^2/m^3].
    eps : float
        Dry-bed void fraction [-].
    dP_irr_per_Z, Z, rho_l :
        Irrigated pressure-drop gradient [Pa/m], packed height [m] and
        liquid density [kg/m^3].  When all three are given, the
        loading-region correction is applied; otherwise the pre-loading
        value ``h0`` is returned.
    mu_l : float, optional
        Liquid viscosity [Pa*s]; a warning is issued above 5 mPa*s, the
        upper bound of the correlation's validation range.

    Returns
    -------
    dict
        ``Fr_L``, ``h0`` (pre-loading), ``h_L`` (actual) -- all volume
        fractions [m^3/m^3].

    Notes
    -----
    ``h0 = 0.555 * Fr_L**(1/3)`` with
    ``Fr_L = u_L^2 * a_p / (g * eps**4.65)`` and
    ``h_L = h0 * [1 + 20 * (dP_irr/Z / (rho_L g))**2]``.
    Cross-confirmed by six independent documents including an executable
    MATLAB listing (see the cited design note sec. 3).  The pressure-drop-side
    packing constants C1/C2/C3 have conflicting published values and are
    **not** used here.
    """
    if u_l < 0:
        raise ValueError("u_l must be non-negative")
    if not 0.0 < eps < 1.0:
        raise ValueError(f"eps must lie in (0, 1); got {eps}")
    if a_p <= 0:
        raise ValueError("a_p must be > 0")
    if mu_l is not None and mu_l > 5e-3:
        warnings.warn(
            "Stichlmair-Bravo-Fair (1989) was validated up to "
            "mu_L = 5 mPa*s; current liquid viscosity exceeds that",
            UserWarning,
            stacklevel=2,
        )

    fr_l = u_l**2 * a_p / (_G * eps**4.65)
    h0 = 0.555 * fr_l ** (1.0 / 3.0)
    h_l = h0
    if dP_irr_per_Z is not None and Z is not None and rho_l is not None:
        if Z <= 0:
            raise ValueError("Z must be > 0")
        h_l = h0 * (1.0 + 20.0 * (dP_irr_per_Z / (Z * rho_l * _G)) ** 2)
    h_l = min(h_l, 0.5)  # same numerical guard as the ChemSep implementation
    return {"Fr_L": fr_l, "h0": h0, "h_L": h_l}


# ----------------------------------------------------------------------
# packed columns -- Billet & Schultes (substitute for "Bravo-Fair 1982")
# ----------------------------------------------------------------------


def liquid_holdup_packed_billet_schultes(
    u_l: float,
    a_p: float,
    rho_l: float,
    mu_l: float,
    c_h: float,
    *,
    u_v: float | None = None,
    u_v_flood: float | None = None,
    eps: float | None = None,
    rho_w: float = 997.0,
    mu_w: float = 1.0e-3,
) -> dict:
    """Billet-Schultes liquid holdup for random / structured packings.

    Implemented as the recommended substitute for the declared basis's
    "Bravo & Fair (1982)" entry, which contains no holdup correlation (see
    the cited design note sec. 4).  Formula family as given in the ChemSep Book
    (Eq. 16.53-16.64), verified against three independent documents.

    Parameters
    ----------
    u_l : float
        Superficial liquid velocity [m/s].
    a_p : float
        Packing specific surface area [m^2/m^3].
    rho_l, mu_l : float
        Liquid density [kg/m^3] and viscosity [Pa*s].
    c_h : float
        Packing-specific hydraulic constant ``C_h`` (required; values are
        tabulated per packing in the Billet-Schultes literature).
    u_v, u_v_flood, eps :
        Optional above-loading correction inputs: vapour velocity [m/s],
        its flooding value, and the packing void fraction.  When given,
        ``h_L = h_L,pl + (h_L,fl - h_L,pl) * (u_v/u_v_flood)**13``.  When
        ``u_v > u_v_flood`` the result is extrapolated beyond the
        correlation's validity range: a ``UserWarning`` is emitted and the
        returned value is **not** clipped or otherwise altered.
    rho_w, mu_w :
        Reference water properties for the flooding-holdup term.

    Returns
    -------
    dict
        ``Re_L``, ``Fr_L``, ``a_h_over_a_p``, ``h_L``.
    """
    if u_l < 0 or a_p <= 0 or rho_l <= 0 or mu_l <= 0 or c_h <= 0:
        raise ValueError("u_l >= 0 and a_p, rho_l, mu_l, c_h > 0 required")

    re_l = u_l * rho_l / (a_p * mu_l)
    fr_l = u_l**2 * a_p / _G
    if re_l < 5.0:
        a_h = c_h * re_l**0.15 * fr_l**0.1
    else:
        a_h = 0.85 * c_h * re_l**0.25 * fr_l**0.1
    h_l_pl = (12.0 * mu_l * a_p**2 * u_l / (rho_l * _G)) ** (1.0 / 3.0) * a_h ** (
        2.0 / 3.0
    )
    out = {"Re_L": re_l, "Fr_L": fr_l, "a_h_over_a_p": a_h, "h_L": h_l_pl}

    if u_v is not None and u_v_flood is not None and eps is not None:
        if not 0.0 < u_v_flood:
            raise ValueError("u_v_flood must be > 0")
        if u_v > u_v_flood:
            warnings.warn(
                f"vapour velocity {u_v:.4g} m/s exceeds the Billet-Schultes "
                f"flooding velocity {u_v_flood:.4g} m/s; the correlation is "
                f"extrapolated beyond its validity range",
                UserWarning,
                stacklevel=2,
            )
        h_fl = 0.3741 * eps * (mu_l * rho_w / (mu_w * rho_l)) ** 0.05
        h_l_s = h_l_pl + (h_fl - h_l_pl) * (u_v / u_v_flood) ** 13.0
        out["h_L_flood"] = h_fl
        out["h_L"] = h_l_s
    return out


# ----------------------------------------------------------------------
# structured packing -- Rocha, Bravo & Fair (1993)
# ----------------------------------------------------------------------


def liquid_holdup_packed_rocha_bravo_fair(
    u_ls: float,
    u_gs: float,
    rho_l: float,
    rho_g: float,
    mu_l: float,
    sigma: float,
    *,
    corrugation_base_m: float,
    corrugation_height_m: float,
    corrugation_angle_deg: float,
    eps: float,
    a_p: float | None = None,
    f_se: float = 0.35,
    dP_per_Z: float | None = None,
    dP_per_Z_flood: float = 1025.0,
    include_eps_in_denom: bool = True,
    sigma_switch_n_m: float = 0.055,
) -> dict:
    """Rocha-Bravo-Fair (1993) total liquid holdup, structured packings.

    ``h_L = (4 Ft / S)**(2/3) * [3 mu_L u_LS / (rho_L g_eff sin(theta))]**(1/3)``
    with the area-correction factor ``Ft`` as published (cross-confirmed by
    five independent documents plus an executable MATLAB listing; see the
    the cited design note sec. 5).

    Parameters
    ----------
    u_ls, u_gs : float
        Superficial (empty-column) liquid / vapour velocities [m/s].
    rho_l, rho_g, mu_l, sigma :
        Fluid properties (SI; ``sigma`` in N/m).
    corrugation_base_m, corrugation_height_m, corrugation_angle_deg :
        Corrugation geometry; ``S = sqrt(b^2/4 + h^2)`` [m].
    eps : float
        Packing void fraction.
    a_p : float, optional
        Specific surface area, only needed for ``a_e``.
    f_se : float
        Surface-enhancement factor (0.35 for Mellapak/Flexipac).
    dP_per_Z : float, optional
        Current pressure-drop gradient [Pa/m]; when given, ``g_eff``
        includes the flooding-margin term.  **Coupling note:** in a
        simulator this must be iterated with the pressure-drop model
        (relaxation 0.5 recommended); this function performs a single
        evaluation.
    dP_per_Z_flood : float
        Flooding pressure drop [Pa/m] (1025 for air/water; packing- and
        load-dependent -- 1650 has been reported for Mellapak 350Y at
        high load).
    include_eps_in_denom : bool
        Definitional switch for the published dispute (Qiu comment vs
        authors' rebuttal): ``True`` (default, matches the executable
        UFRJ listing) uses the bed-volume convention with ``eps`` in the
        denominator; ``False`` reproduces the five printed variants.
    sigma_switch_n_m : float
        Contact-angle switch point: ``cos(gamma) = 0.9`` below it, the
        published exponential above it.  The original paper uses 0.055;
        the ChemSep implementation uses 0.0453 N/m to keep ``cos(gamma)``
        continuous.

    Returns
    -------
    dict
        ``S``, ``Re_L``, ``We_L``, ``Fr_L``, ``cos_gamma``, ``g_eff``,
        ``Ft``, ``h_L`` (volume fraction per the chosen convention),
        ``a_e`` (when ``a_p`` given).
    """
    if not 0.0 < eps < 1.0:
        raise ValueError(f"eps must lie in (0, 1); got {eps}")
    if rho_l <= rho_g:
        raise ValueError("liquid density must exceed vapour density")
    if mu_l <= 0 or sigma <= 0:
        raise ValueError("mu_l and sigma must be > 0")
    if u_ls < 0 or u_gs < 0:
        raise ValueError("velocities must be non-negative")

    s = math.sqrt(corrugation_base_m**2 / 4.0 + corrugation_height_m**2)
    sin_t = math.sin(math.radians(corrugation_angle_deg))

    cos_gamma = 0.9 if sigma < sigma_switch_n_m else 5.211 * 10 ** (-16.835 * sigma)
    re_l = u_ls * rho_l * s / mu_l
    we_l = u_ls**2 * rho_l * s / sigma
    fr_l = u_ls**2 / (s * _G)
    # avoid division by zero at standstill; settle to 0 contribution
    if re_l <= 0 or we_l <= 0 or fr_l <= 0:
        return {
            "S": s,
            "Re_L": re_l,
            "We_L": we_l,
            "Fr_L": fr_l,
            "cos_gamma": cos_gamma,
            "g_eff": _G * (rho_l - rho_g) / rho_l,
            "Ft": 0.0,
            "h_L": 0.0,
        }
    ft = (29.12 * (we_l * fr_l) ** 0.15 * s**0.359) / (
        re_l**0.2 * eps**0.6 * sin_t**0.3 * (1.0 - 0.93 * cos_gamma)
    )
    g_eff = _G * (rho_l - rho_g) / rho_l
    if dP_per_Z is not None:
        if dP_per_Z >= dP_per_Z_flood:
            raise ValueError(
                "at or beyond the flooding pressure drop "
                f"({dP_per_Z} >= {dP_per_Z_flood} Pa/m): the Rocha-Bravo-Fair "
                "holdup model is only valid below the loading point"
            )
        g_eff *= 1.0 - dP_per_Z / dP_per_Z_flood

    denom = rho_l * g_eff * sin_t
    if include_eps_in_denom:
        denom *= eps
    h_l = (4.0 * ft / s) ** (2.0 / 3.0) * (3.0 * mu_l * u_ls / denom) ** (1.0 / 3.0)
    h_l = min(h_l, 0.5)  # numerical guard below the loading point
    out = {
        "S": s,
        "Re_L": re_l,
        "We_L": we_l,
        "Fr_L": fr_l,
        "cos_gamma": cos_gamma,
        "g_eff": g_eff,
        "Ft": ft,
        "h_L": h_l,
    }
    if a_p is not None:
        out["a_e"] = ft * f_se * a_p
    return out


def vapor_holdup_packed(
    eps: float, h_l: float, area_m2: float, height_m: float
) -> float:
    """Vapour holdup volume in a packed section [m^3]:
    ``V_V = (eps - h_L) * A * Z``.
    """
    if not 0.0 < eps < 1.0:
        raise ValueError(f"eps must lie in (0, 1); got {eps}")
    if h_l < 0:
        raise ValueError("h_l must be non-negative")
    if h_l >= eps:
        warnings.warn(
            f"liquid holdup {h_l:.4f} >= void fraction {eps:.4f}; "
            "vapour holdup clipped at 0 (flooding)",
            UserWarning,
            stacklevel=2,
        )
        return 0.0
    return (eps - h_l) * area_m2 * height_m


# ----------------------------------------------------------------------
# column-level evaluation
# ----------------------------------------------------------------------


@dataclass
class ColumnHoldupResult:
    """Per-stage holdup of a solved column (mixture totals, not tritium-
    weighted -- the tritium inventory conversion lives in
    :mod:`h2iso.inventory`)."""

    liquid_mol_per_stage: np.ndarray  # (N,) mol
    vapor_mol_per_stage: np.ndarray  # (N,) mol
    method_liquid: str
    total_liquid_mol: float
    total_vapor_mol: float
    liquid_volume_m3_per_stage: np.ndarray | None = None  # (N,) m^3
    vapor_volume_m3_per_stage: np.ndarray | None = None  # (N,) m^3
    liquid_molar_volume_m3_per_mol: np.ndarray | None = None  # (N,) m^3/mol

    def to_dict(self) -> dict:
        out = {
            "method_liquid": self.method_liquid,
            "total_liquid_mol": float(self.total_liquid_mol),
            "total_vapor_mol": float(self.total_vapor_mol),
            "liquid_mol_per_stage": [float(v) for v in self.liquid_mol_per_stage],
            "vapor_mol_per_stage": [float(v) for v in self.vapor_mol_per_stage],
        }
        if self.liquid_volume_m3_per_stage is not None:
            out["liquid_volume_m3_per_stage"] = [
                float(v) for v in self.liquid_volume_m3_per_stage
            ]
        return out


_GAS_R = 8.314462618  # J/(mol K)
# end-stage liquid fractions (same convention as h2iso.inventory)
_EPS_CONDENSER = 0.01
_EPS_REBOILER = 0.05


def _stage_properties(T, x, y, pressure, molar_volumes, species_masses):
    """Mixture properties for one stage: densities [kg/m3], molar masses."""
    m_l = float(np.dot(x, species_masses)) * 1e-3  # kg/mol
    m_v = float(np.dot(y, species_masses)) * 1e-3
    v_l = max(float(np.dot(x, molar_volumes)), 1e-12)  # m3/mol
    rho_l = m_l / v_l
    rho_v = pressure * m_v / (_GAS_R * T)
    return rho_l, rho_v, m_l, m_v, v_l


def evaluate_column_holdup(
    result,
    geometry: ColumnGeometry,
    *,
    pressure: float = 101325.0,
    molar_volumes: dict | None = None,
    tray_method: str = "bennett-agrawal",
    packed_method: str = "stichlmair",
    packed_extra: dict | None = None,
) -> ColumnHoldupResult:
    """Compute per-stage liquid/vapour holdup [mol] for a solved column.

    Parameters
    ----------
    result : h2iso.mesh.column.ColumnResult
        Solved column profiles (``T_profile``, ``x_profile``, ``y_profile``,
        ``L_profile``, ``V_profile``).
    geometry : ColumnGeometry
        Hardware description; must satisfy ``validate(for_holdup=True)``
        for the chosen method.
    pressure : float
        Operating pressure [Pa] (uniform; matches the CMO solver).
    molar_volumes : dict, optional
        Liquid molar volumes per species [m^3/mol]; defaults to the
        Wang (2022) Table 7 values used by :mod:`h2iso.inventory`.
    tray_method : {"bennett-agrawal", "hofhuis-zuiderweg"}
    packed_method : {"stichlmair", "billet-schultes", "rocha-bravo-fair"}
    packed_extra : dict, optional
        Extra keyword arguments for the packed correlation (e.g. ``c_h``
        for Billet-Schultes, corrugation geometry for Rocha-Bravo-Fair).

    Node conventions
    ----------------
    Stage 0 (total condenser) and stage N-1 (reboiler) use the volume
    fractions ``eps_cond = 0.01`` / ``eps_reb = 0.05`` (same defaults as
    the inventory module).  Internal tray stages use the chosen tray
    correlation; packed stages treat each *theoretical* stage as a packed
    height of one HETP.
    """
    from h2iso.species import SPECIES, SPECIES_ORDER

    if molar_volumes is None:
        from h2iso.inventory.models import DEFAULT_MOLAR_VOLUMES

        molar_volumes = DEFAULT_MOLAR_VOLUMES

    species_masses = np.array([SPECIES[sp].molar_mass for sp in SPECIES_ORDER])
    v_vec = np.array([molar_volumes.get(sp, 2.5e-5) for sp in SPECIES_ORDER])

    T_prof = np.asarray(result.T_profile)
    x_prof = np.asarray(result.x_profile)
    y_prof = np.asarray(result.y_profile)
    L_prof = np.asarray(result.L_profile)
    V_prof = np.asarray(result.V_profile)
    N = len(T_prof)

    geometry.validate()
    holdup_l = np.zeros(N)
    holdup_v = np.zeros(N)
    vol_l_arr = np.zeros(N)
    vol_v_arr = np.zeros(N)
    v_mol_arr = np.zeros(N)

    # --- end stages: volume-based estimate (inventory convention) ---
    for j, eps_frac in ((0, _EPS_CONDENSER), (N - 1, _EPS_REBOILER)):
        vol = geometry.condenser_volume_m3 if j == 0 else geometry.reboiler_volume_m3
        if vol is None:
            warnings.warn(
                f"no volume given for stage {j + 1} "
                f"({'condenser' if j == 0 else 'reboiler'}); holdup set to 0",
                UserWarning,
                stacklevel=2,
            )
            continue
        rho_l, rho_v, m_l, m_v, v_l = _stage_properties(
            T_prof[j], x_prof[j], y_prof[j], pressure, v_vec, species_masses
        )
        v_mol_arr[j] = v_l
        vol_l_arr[j] = vol * eps_frac
        vol_v_arr[j] = vol * (1.0 - eps_frac)
        holdup_l[j] = vol * eps_frac * rho_l / m_l
        holdup_v[j] = pressure * vol * (1.0 - eps_frac) / (_GAS_R * T_prof[j])

    # --- contact stages ---
    if geometry.column_type == "tray":
        method = tray_method
        for j in range(1, N - 1):
            rho_l, rho_v, m_l, m_v, v_l = _stage_properties(
                T_prof[j], x_prof[j], y_prof[j], pressure, v_vec, species_masses
            )
            q_l = L_prof[j] * v_l / 3600.0
            q_v = V_prof[j] * (_GAS_R * T_prof[j] / pressure) / 3600.0
            v_mol_arr[j] = v_l
            if method == "bennett-agrawal":
                hyd = liquid_holdup_tray_bennett_agrawal(
                    geometry, q_l, q_v, rho_l, rho_v
                )
                froth = hyd.froth_height_m
            elif method == "hofhuis-zuiderweg":
                hyd = liquid_holdup_tray_hofhuis_zuiderweg(
                    geometry, q_l, q_v, rho_l, rho_v
                )
                froth = hyd.h_clear_liquid_m / 0.5  # fallback froth estimate
            else:
                raise ValueError(f"unknown tray_method {method!r}")
            holdup_l[j] = hyd.liquid_volume_m3 * rho_l / m_l
            v_v = vapor_holdup_tray(geometry, froth, hyd.active_area_m2)
            holdup_v[j] = v_v * rho_v / m_v
            vol_l_arr[j] = hyd.liquid_volume_m3
            vol_v_arr[j] = v_v
        method_liquid = f"tray:{method}"
    elif geometry.column_type == "packed":
        geometry.validate(for_holdup=True)
        if geometry.hetp_m is None:
            raise ValueError(
                "packed holdup requires geometry.hetp_m (height per theoretical stage)"
            )
        area = geometry.cross_section_area_m2
        h_stage = geometry.hetp_m
        extra = packed_extra or {}
        method = packed_method
        for j in range(1, N - 1):
            rho_l, rho_v, m_l, m_v, v_l = _stage_properties(
                T_prof[j], x_prof[j], y_prof[j], pressure, v_vec, species_masses
            )
            q_l = L_prof[j] * v_l / 3600.0
            u_l = q_l / area
            v_mol_arr[j] = v_l
            if method == "stichlmair":
                out = liquid_holdup_packed_stichlmair(
                    u_l,
                    geometry.packing_specific_area_m2_m3,
                    geometry.packing_void_fraction,
                )
                h_l = out["h_L"]
            elif method == "billet-schultes":
                bs_kwargs = dict(extra)
                mu_l = bs_kwargs.pop("mu_l", 1.3e-5)  # liquid-H2 order default
                out = liquid_holdup_packed_billet_schultes(
                    u_l,
                    geometry.packing_specific_area_m2_m3,
                    rho_l,
                    mu_l,
                    **bs_kwargs,
                )
                h_l = out["h_L"]
            elif method == "rocha-bravo-fair":
                out = liquid_holdup_packed_rocha_bravo_fair(
                    u_ls=u_l,
                    u_gs=V_prof[j] * (_GAS_R * T_prof[j] / pressure) / 3600.0 / area,
                    rho_l=rho_l,
                    rho_g=rho_v,
                    **extra,
                )
                h_l = out["h_L"]
            else:
                raise ValueError(f"unknown packed_method {method!r}")
            vol_l = h_l * area * h_stage
            v_v = vapor_holdup_packed(
                geometry.packing_void_fraction, h_l, area, h_stage
            )
            holdup_l[j] = vol_l * rho_l / m_l
            holdup_v[j] = v_v * rho_v / m_v
            vol_l_arr[j] = vol_l
            vol_v_arr[j] = v_v
        method_liquid = f"packed:{method}"
    else:
        raise ValueError(
            "column_type='theoretical' has no hydraulics; provide a packed "
            "or tray ColumnGeometry to compute holdup"
        )
    return ColumnHoldupResult(
        liquid_mol_per_stage=holdup_l,
        vapor_mol_per_stage=holdup_v,
        method_liquid=method_liquid,
        total_liquid_mol=float(holdup_l.sum()),
        total_vapor_mol=float(holdup_v.sum()),
        liquid_volume_m3_per_stage=vol_l_arr,
        vapor_volume_m3_per_stage=vol_v_arr,
        liquid_molar_volume_m3_per_mol=v_mol_arr,
    )


# ----------------------------------------------------------------------
# bridge to the h2iso.inventory (Wang 2022 six-zone) model
# ----------------------------------------------------------------------


def bridge_holdup_to_inventory(
    holdup: ColumnHoldupResult,
    geometry: ColumnGeometry,
    *,
    base=None,
) -> dict:
    """Express the detailed holdup as effective epsilon factors of the
    Wang (2022) six-zone inventory model.

    The inventory model (``h2iso.inventory``) uses fixed volume fractions:
    ``eps_condenser`` (liquid fraction of the condenser drum),
    ``eps_packing * eps_stage`` (liquid fraction of one theoretical-stage
    volume in the packed section) and ``eps_reboiler``.  This bridge
    derives equivalent values from the detailed per-stage holdup so that
    :func:`h2iso.inventory.evaluate_column_inventory` can be driven with
    hydraulics-based (rather than empirical) holdup.

    Parameters
    ----------
    holdup : ColumnHoldupResult
        Result of :func:`evaluate_column_holdup` for a **packed** column
        (the inventory model is packed-section based).
    geometry : ColumnGeometry
        The same geometry used for the holdup evaluation.
    base : InventoryGeometry, optional
        Base inventory geometry (volumes, packing fraction); defaults to
        :class:`h2iso.inventory.InventoryGeometry` built from ``geometry``.

    Returns
    -------
    dict
        ``eps_condenser``, ``eps_stage``, ``eps_reboiler``, ``eps_packing``
        plus a ``note`` documenting the convention.  Feed straight into
        :func:`apply_bridge_to_inventory_geometry`.

    Notes
    -----
    Convention: the inventory model computes the stage liquid volume as
    ``V_stage * eps_packing * eps_stage`` with ``V_stage = A * HETP``.
    The bridge chooses ``eps_stage`` so that the inventory model
    reproduces the **total** detailed liquid moles of the packed section
    (integral-consistent, using the per-stage liquid molar volumes);
    ``eps_packing`` itself is kept from the base geometry.  End stages
    map through their drum volumes.  Note this is a single equivalent
    value per section -- the inventory model has no per-stage resolution.
    """
    from h2iso.inventory.models import InventoryGeometry

    if geometry.column_type != "packed":
        raise ValueError(
            "the inventory bridge is defined for packed columns; tray "
            "columns are not represented by the six-zone inventory model"
        )
    if holdup.liquid_volume_m3_per_stage is None:
        raise ValueError("holdup result carries no volume profiles")
    if geometry.hetp_m is None or geometry.diameter_m is None:
        raise ValueError("geometry.hetp_m and diameter_m are required")
    if not math.isfinite(geometry.hetp_m) or geometry.hetp_m <= 0.0:
        raise ValueError(
            f"geometry.hetp_m must be finite and > 0; got {geometry.hetp_m!r}"
        )
    if not math.isfinite(geometry.diameter_m) or geometry.diameter_m <= 0.0:
        raise ValueError(
            f"geometry.diameter_m must be finite and > 0; got {geometry.diameter_m!r}"
        )

    if base is None:
        base = InventoryGeometry(
            inside_diameter_m=geometry.diameter_m,
            HETP_m=geometry.hetp_m,
            condenser_volume_m3=geometry.condenser_volume_m3 or 1.0e-3,
            reboiler_volume_m3=geometry.reboiler_volume_m3 or 2.0e-4,
        )

    if not math.isfinite(base.eps_packing) or base.eps_packing <= 0.0:
        raise ValueError(
            f"base.eps_packing must be finite and > 0; got {base.eps_packing!r}"
        )

    v_stage = geometry.cross_section_area_m2 * geometry.hetp_m
    internal = np.asarray(holdup.liquid_volume_m3_per_stage)[1:-1]
    if internal.size > 0:
        v_mol = holdup.liquid_molar_volume_m3_per_mol
        if v_mol is not None:
            # integral-consistent choice: pick eps_stage such that
            # sum_j V_stage*eps_packing*eps_stage / v_j  ==  sum_j V_L,j / v_j
            # (i.e. the inventory model reproduces the detailed liquid moles)
            v_int = np.asarray(v_mol)[1:-1]
            num = float(np.sum(internal / v_int))
            den = float(np.sum(v_stage / v_int))
            eps_stage = num / den / base.eps_packing
        else:
            eps_stage = float(np.mean(internal) / v_stage / base.eps_packing)
    else:
        eps_stage = base.eps_stage
    eps_condenser = (
        float(holdup.liquid_volume_m3_per_stage[0] / base.condenser_volume_m3)
        if base.condenser_volume_m3
        else base.eps_condenser
    )
    eps_reboiler = (
        float(holdup.liquid_volume_m3_per_stage[-1] / base.reboiler_volume_m3)
        if base.reboiler_volume_m3
        else base.eps_reboiler
    )
    return {
        "eps_condenser": eps_condenser,
        "eps_stage": eps_stage,
        "eps_reboiler": eps_reboiler,
        "eps_packing": base.eps_packing,
        "note": (
            "bridge from h2iso.mesh.holdup; eps_stage = mean(V_L/V_stage)/"
            "eps_packing over internal stages; end stages from drum volumes"
        ),
    }


def apply_bridge_to_inventory_geometry(bridge: dict, base=None):
    """Return a copy of an InventoryGeometry with the bridged epsilons.

    ``base`` defaults to :class:`h2iso.inventory.InventoryGeometry` with
    default dimensions; pass the same base used for
    :func:`bridge_holdup_to_inventory` to keep consistency.
    """
    from dataclasses import replace

    from h2iso.inventory.models import InventoryGeometry

    if base is None:
        base = InventoryGeometry()
    return replace(
        base,
        eps_condenser=float(bridge["eps_condenser"]),
        eps_stage=float(bridge["eps_stage"]),
        eps_reboiler=float(bridge["eps_reboiler"]),
        eps_packing=float(bridge.get("eps_packing", base.eps_packing)),
    )
