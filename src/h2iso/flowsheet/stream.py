"""Stream data structure and operations for flowsheet modeling."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from h2iso.species import N_SPECIES


@dataclass
class Stream:
    """A process stream in the flowsheet.

    Attributes
    ----------
    flow : float
        Molar flow rate (mol/h).
    composition : ndarray of shape (6,)
        Mole fractions of [H2, HD, HT, D2, DT, T2].
    temperature : float
        Temperature (K).
    pressure : float
        Pressure (Pa).
    phase : str
        Phase: "liquid", "vapor", or "two-phase".
    """

    flow: float
    composition: np.ndarray
    temperature: float
    pressure: float
    phase: str = "liquid"

    def __post_init__(self):
        self.composition = np.asarray(self.composition, dtype=float)
        if self.composition.shape != (N_SPECIES,):
            raise ValueError(f"composition must have shape ({N_SPECIES},)")
        self._validate_composition()

    def _validate_composition(self) -> None:
        """Reject malformed compositions before they pollute the solver.

        Tolerances are loose enough to accept NLP solver round-off (~1e-9)
        but tight enough to catch genuinely wrong data such as a -0.1 entry
        or a composition that does not sum to 1.
        """
        comp = self.composition
        neg_tol = 1e-8
        sum_tol = 1e-6
        if np.any(comp < -neg_tol):
            raise ValueError(
                f"composition must be non-negative (tolerance {neg_tol:.0e}); "
                f"got min={float(comp.min()):.3e}"
            )
        total = float(comp.sum())
        if abs(total - 1.0) > sum_tol:
            raise ValueError(
                f"composition must sum to 1.0 within {sum_tol:.0e}; "
                f"got sum={total:.12g}"
            )


def stream_mix(streams: list[Stream]) -> Stream:
    """Mix multiple streams into one.

    Uses flow-weighted average composition and temperature.
    Pressure is taken from the first stream (assumes isobaric mixing).

    Parameters
    ----------
    streams : list of Stream
        Streams to mix.

    Returns
    -------
    Stream
        Mixed stream.
    """
    if not streams:
        raise ValueError("Cannot mix empty list of streams")

    total_flow = sum(s.flow for s in streams)
    if total_flow <= 0:
        raise ValueError("Total flow must be positive")

    # Flow-weighted composition
    z_mix = np.zeros(N_SPECIES)
    T_mix = 0.0
    for s in streams:
        z_mix += s.flow * s.composition
        T_mix += s.flow * s.temperature
    z_mix /= total_flow
    T_mix /= total_flow

    return Stream(
        flow=total_flow,
        composition=z_mix,
        temperature=T_mix,
        pressure=streams[0].pressure,
        phase=streams[0].phase,
    )


def stream_split(stream: Stream, ratios: list[float]) -> list[Stream]:
    """Split a stream into multiple streams by flow ratios.

    Parameters
    ----------
    stream : Stream
        Source stream to split.
    ratios : list of float
        Split ratios (will be normalized to sum to 1).

    Returns
    -------
    list of Stream
        Split streams with same composition/temperature/pressure.
    """
    if not ratios:
        raise ValueError("ratios must be non-empty")

    total = sum(ratios)
    if total <= 0:
        raise ValueError("Sum of ratios must be positive")

    fracs = [r / total for r in ratios]
    return [
        Stream(
            flow=stream.flow * f,
            composition=stream.composition.copy(),
            temperature=stream.temperature,
            pressure=stream.pressure,
            phase=stream.phase,
        )
        for f in fracs
    ]
