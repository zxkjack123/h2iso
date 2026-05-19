"""Unit operation abstractions for flowsheet modeling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from h2iso.equilibrator.exchange import atom_fractions, equilibrium_composition
from h2iso.flowsheet.stream import Stream, stream_mix
from h2iso.mesh.column import Column, ColumnSpec, FeedSpec
from h2iso.mesh.continuation import ContinuationSolver
from h2iso.species import N_SPECIES


@dataclass
class UnitOp(ABC):
    """Abstract base class for unit operations."""

    name: str
    inlets: dict[str, Stream] = field(default_factory=dict)
    outlets: dict[str, Stream] = field(default_factory=dict)

    @abstractmethod
    def solve(self, inputs: dict[str, Stream]) -> dict[str, Stream]:
        """Solve the unit given input streams.

        Parameters
        ----------
        inputs : dict[str, Stream]
            Named input streams.

        Returns
        -------
        dict[str, Stream]
            Named output streams.
        """


@dataclass
class ColumnUnit(UnitOp):
    """Distillation column unit wrapping Column + ContinuationSolver.

    Parameters
    ----------
    name : str
        Unit name.
    n_stages : int
        Number of theoretical stages.
    pressure : float
        Column pressure (Pa).
    reflux_ratio : float
        Reflux ratio.
    distillate_to_feed : float
        D/F ratio.
    feed_stages : list[int] | None
        Stage indices for each feed (1-indexed). If None, single feed at middle.
    continuation_substeps : int
        Number of substeps for continuation from small N. 0 = direct solve.
    """

    n_stages: int = 20
    pressure: float = 101325.0
    reflux_ratio: float = 5.0
    distillate_to_feed: float = 0.5
    feed_stages: list[int] | None = None
    continuation_substeps: int = 0

    def solve(self, inputs: dict[str, Stream]) -> dict[str, Stream]:
        """Solve column with given feed streams.

        Input keys are used as feed identifiers. Output keys: "distillate", "bottoms".
        """
        # Collect feeds
        feed_streams = list(inputs.values())
        if not feed_streams:
            raise ValueError(f"ColumnUnit '{self.name}': no input streams")

        # Determine feed stages
        if self.feed_stages is not None:
            if len(self.feed_stages) != len(feed_streams):
                raise ValueError(
                    f"feed_stages length ({len(self.feed_stages)}) != "
                    f"number of inputs ({len(feed_streams)})"
                )
            stages = self.feed_stages
        else:
            # Default: evenly spaced
            n_feeds = len(feed_streams)
            stages = [
                max(2, min(self.n_stages - 1, int((i + 1) * self.n_stages / (n_feeds + 1))))
                for i in range(n_feeds)
            ]

        # Build FeedSpec list
        feeds = [
            FeedSpec(
                stage=stages[i],
                flow=feed_streams[i].flow,
                composition=feed_streams[i].composition,
                quality=1.0,
            )
            for i in range(len(feed_streams))
        ]

        total_flow = sum(f.flow for f in feeds)
        z_avg = np.zeros(N_SPECIES)
        for f in feeds:
            z_avg += f.flow * f.composition
        z_avg /= total_flow

        spec = ColumnSpec(
            n_stages=self.n_stages,
            feed_stage=stages[0],
            feed_flow=total_flow,
            feed_composition=z_avg,
            pressure=self.pressure,
            reflux_ratio=self.reflux_ratio,
            distillate_to_feed=self.distillate_to_feed,
            feeds=feeds if len(feeds) > 1 else None,
        )

        # Solve with or without continuation
        if self.continuation_substeps > 0 and self.n_stages > 20:
            base_N = 15
            base_feeds = ContinuationSolver._scale_feeds(spec, base_N)
            base_feed_stage = max(2, min(base_N - 1, int(stages[0] / self.n_stages * base_N)))
            base_spec = ColumnSpec(
                n_stages=base_N,
                feed_stage=base_feed_stage,
                feed_flow=total_flow,
                feed_composition=z_avg,
                pressure=self.pressure,
                reflux_ratio=self.reflux_ratio,
                distillate_to_feed=self.distillate_to_feed,
                feeds=base_feeds,
            )
            solver = ContinuationSolver()
            solver.add_step("N", target=self.n_stages, n_substeps=self.continuation_substeps)
            cont_result = solver.solve(base_spec)
            result = cont_result.final
        else:
            col = Column(spec)
            result = col.solve()

        if not result.convergence_info["success"]:
            raise RuntimeError(
                f"ColumnUnit '{self.name}' failed: {result.convergence_info['status']}"
            )

        # Extract outputs
        D_flow = self.distillate_to_feed * total_flow
        B_flow = total_flow - D_flow

        self.inlets = inputs
        self.outlets = {
            "distillate": Stream(
                flow=D_flow,
                composition=result.x_profile[0],
                temperature=result.T_profile[0],
                pressure=self.pressure,
                phase="liquid",
            ),
            "bottoms": Stream(
                flow=B_flow,
                composition=result.x_profile[-1],
                temperature=result.T_profile[-1],
                pressure=self.pressure,
                phase="liquid",
            ),
        }
        return self.outlets


@dataclass
class EquilibratorUnit(UnitOp):
    """Catalytic equilibrator for isotope exchange.

    Establishes chemical equilibrium among the 6 hydrogen isotopologues
    at the given temperature.
    """

    temperature: float = 25.0  # K

    def solve(self, inputs: dict[str, Stream]) -> dict[str, Stream]:
        """Equilibrate the mixed input stream."""
        mixed = stream_mix(list(inputs.values()))

        # Get atom fractions from current composition
        aH, aD, aT = atom_fractions(mixed.composition)

        # Compute equilibrium at unit temperature
        T_eq = self.temperature if self.temperature > 0 else mixed.temperature
        x_eq = equilibrium_composition(aH, aD, aT, T=T_eq)

        self.inlets = inputs
        self.outlets = {
            "out": Stream(
                flow=mixed.flow,
                composition=x_eq,
                temperature=T_eq,
                pressure=mixed.pressure,
                phase=mixed.phase,
            )
        }
        return self.outlets


@dataclass
class MixerUnit(UnitOp):
    """Mixer: combines multiple streams into one."""

    def solve(self, inputs: dict[str, Stream]) -> dict[str, Stream]:
        """Mix all input streams."""
        mixed = stream_mix(list(inputs.values()))
        self.inlets = inputs
        self.outlets = {"out": mixed}
        return self.outlets


@dataclass
class SplitterUnit(UnitOp):
    """Splitter: divides one stream into multiple by flow ratios.

    Parameters
    ----------
    ratios : dict[str, float]
        Named output streams with their flow ratios.
    """

    ratios: dict[str, float] = field(default_factory=dict)

    def solve(self, inputs: dict[str, Stream]) -> dict[str, Stream]:
        """Split the single input stream by ratios."""
        if len(inputs) != 1:
            raise ValueError(f"SplitterUnit expects 1 input, got {len(inputs)}")

        source = next(iter(inputs.values()))
        if not self.ratios:
            raise ValueError("SplitterUnit ratios must be set")

        total_ratio = sum(self.ratios.values())
        self.inlets = inputs
        self.outlets = {}
        for name, ratio in self.ratios.items():
            frac = ratio / total_ratio
            self.outlets[name] = Stream(
                flow=source.flow * frac,
                composition=source.composition.copy(),
                temperature=source.temperature,
                pressure=source.pressure,
                phase=source.phase,
            )
        return self.outlets
