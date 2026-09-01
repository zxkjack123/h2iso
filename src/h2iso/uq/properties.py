"""Global property perturbation for UQ (P01-P05).

Provides a context manager that temporarily overrides module-level
property globals (Souers vapor pressure parameters and BIPs) so that
UQ samples can include thermodynamic uncertainty.

Perturbable parameters follow the naming convention:
  ``"souers.{species}.{coeff}"``  e.g. ``"souers.D2.C1"``
  ``"bip.{i}.{j}"``               e.g. ``"bip.3.4"`` for kij[D2, DT]
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import numpy as np

from h2iso.uq.distributions import Parameter


def _souers_params() -> dict:
    """Return a reference to the souers _PARAMS dict (lazy import)."""
    from h2iso.vle import souers

    return souers._PARAMS  # type: ignore[attr-defined]


def _bip_matrix() -> np.ndarray:
    """Return a reference to the BIP matrix (lazy import)."""
    from h2iso.vle import mixing

    return mixing._KIJ  # type: ignore[attr-defined]


@contextmanager
def property_override(overrides: dict[str, float]):
    """Temporarily override global property parameters.

    Parameters
    ----------
    overrides : dict[str, float]
        Keys like ``"souers.H2.C1"``, ``"bip.3.4"`` mapping to new values.

    Yields
    ------
    None
        The context body runs with modified property globals.
    """
    saved = _apply_overrides(overrides, action="save")
    try:
        yield
    finally:
        _apply_overrides(saved, action="restore")


def _apply_overrides(overrides: dict[str, float], action: str) -> dict[str, Any]:
    """Save or restore global property values."""
    result: dict[str, Any] = {}
    souers_p = _souers_params()
    bip = _bip_matrix()

    for key, value in overrides.items():
        if key.startswith("souers."):
            # Format: "souers.{species}.{coeff}"
            parts = key.split(".", 2)
            if len(parts) != 3:
                raise ValueError(f"Invalid souers key: {key!r}")
            species, coeff = parts[1], parts[2]
            if action == "save":
                if species not in souers_p:
                    raise KeyError(f"Unknown species: {species!r}")
                if coeff not in souers_p[species]:
                    raise KeyError(f"Unknown souers coefficient: {coeff!r}")
                result[key] = souers_p[species][coeff]
                souers_p[species][coeff] = float(value)
            elif action == "restore":
                souers_p[species][coeff] = float(value)

        elif key.startswith("bip."):
            parts = key.split(".")
            i, j = int(parts[1]), int(parts[2])
            if action == "save":
                result[key] = float(bip[i, j])
                bip[i, j] = float(value)
            elif action == "restore":
                bip[i, j] = float(value)

        else:
            raise ValueError(f"Unknown override key: {key!r}")

    return result


def resolve_property_params(
    params: np.ndarray, param_names: list[str]
) -> dict[str, float]:
    """Build an overrides dict from a parameter vector.

    Only keys matching ``"souers.*"`` or ``"bip.*"`` are included.
    Non-property parameters (e.g. CD1.R) are silently ignored.
    """
    return {
        name: float(value)
        for name, value in zip(param_names, params)
        if name.startswith("souers.") or name.startswith("bip.")
    }


def souers_C1_parameter(species: str, sigma_rel: float = 0.01) -> Parameter:
    """Convenience: a normal perturbation on vapor pressure C1.

    Perturbs the dominant coefficient (C1 shifts the whole ln(P) curve).
    """
    sp = _souers_params()
    if species not in sp:
        raise KeyError(f"Unknown species: {species!r}")
    mu = sp[species]["C1"]
    sigma = abs(mu) * sigma_rel
    return Parameter(
        name=f"souers.{species}.C1",
        distribution="normal",
        params={"mu": mu, "sigma": sigma},
        bounds=(mu - 5 * sigma, mu + 5 * sigma),
        description=f"Souers C1 for {species} (σ={sigma_rel:.0%} relative)",
    )


def souers_C2_parameter(species: str, sigma_rel: float = 0.02) -> Parameter:
    """Convenience: a normal perturbation on vapor pressure C2.

    C2 is the inverse-temperature coefficient (Clausius-Clapeyron slope).
    """
    sp = _souers_params()
    if species not in sp:
        raise KeyError(f"Unknown species: {species!r}")
    mu = sp[species]["C2"]
    sigma = abs(mu) * sigma_rel
    return Parameter(
        name=f"souers.{species}.C2",
        distribution="normal",
        params={"mu": mu, "sigma": sigma},
        bounds=(mu - 5 * sigma, mu + 5 * sigma),
        description=f"Souers C2 for {species} (σ={sigma_rel:.0%} relative)",
    )


def bip_parameter(i: int, j: int, mu: float, sigma: float = 0.02) -> Parameter:
    """Convenience: a normal perturbation on a BIP element kij[i,j]."""
    return Parameter(
        name=f"bip.{i}.{j}",
        distribution="normal",
        params={"mu": mu, "sigma": sigma},
        bounds=(mu - 3 * sigma, mu + 3 * sigma),
        description=f"BIP kij[{i},{j}]",
    )
