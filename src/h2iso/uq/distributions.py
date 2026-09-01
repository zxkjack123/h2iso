"""Parameter distributions for UQ propagation.

Wraps scipy.stats distributions with a uniform interface so that
ParameterSpace can sample, perturb, and document each uncertain input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass
class Parameter:
    """A single uncertain parameter.

    Attributes
    ----------
    name : str
        Unique identifier, e.g. ``"CD2.reflux_ratio"``.
    distribution : str
        One of ``"normal"``, ``"lognormal"``, ``"uniform"``.
    params : dict[str, float]
        Distribution parameters:
        - normal: ``{"mu": ..., "sigma": ...}``
        - lognormal: ``{"mu": ..., "sigma": ...}`` (of the underlying normal)
        - uniform: ``{"low": ..., "high": ...}``
    bounds : tuple[float, float] | None
        Optional (lb, ub) clip to physical range. Samples outside are clipped.
    description : str
        Human-readable label for reports.
    """

    name: str
    distribution: str
    params: dict[str, float]
    bounds: tuple[float, float] | None = None
    description: str = ""

    def __post_init__(self) -> None:
        valid = {"normal", "lognormal", "uniform"}
        if self.distribution not in valid:
            raise ValueError(
                f"distribution must be one of {valid}; got {self.distribution!r}"
            )

    def _rv(self) -> stats.rv_continuous:
        if self.distribution == "normal":
            return stats.norm(
                loc=self.params["mu"],
                scale=self.params["sigma"],
            )
        if self.distribution == "lognormal":
            return stats.lognorm(
                s=self.params["sigma"],
                scale=np.exp(self.params["mu"]),
            )
        return stats.uniform(
            loc=self.params["low"],
            scale=self.params["high"] - self.params["low"],
        )

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Draw *n* samples from this parameter's distribution.

        If ``bounds`` is set, values are clipped to the physical range.
        """
        rv = self._rv()
        vals = rv.rvs(size=n, random_state=rng)
        if self.bounds is not None:
            lb, ub = self.bounds
            vals = np.clip(vals, lb, ub)
        return vals

    def ppf(self, quantiles: np.ndarray) -> np.ndarray:
        """Inverse CDF — used by LHS to map unit-interval samples.

        Applies bounds clipping after the inverse CDF.
        """
        rv = self._rv()
        vals = np.asarray(rv.ppf(quantiles), dtype=float)
        if self.bounds is not None:
            lb, ub = self.bounds
            vals = np.clip(vals, lb, ub)
        return vals

    def mean(self) -> float:
        """Theoretical mean (post-clip if bounds are set)."""
        rv = self._rv()
        m = float(rv.mean())
        if self.bounds is not None:
            lb, ub = self.bounds
            m = float(np.clip(m, lb, ub))
        return m

    def to_dict(self) -> dict[str, Any]:
        """Serialise for JSON / YAML config."""
        return {
            "name": self.name,
            "distribution": self.distribution,
            "params": dict(self.params),
            "bounds": list(self.bounds) if self.bounds else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Parameter:
        b = d.get("bounds")
        return cls(
            name=d["name"],
            distribution=d["distribution"],
            params=dict(d["params"]),
            bounds=tuple(b) if b else None,
            description=d.get("description", ""),
        )
