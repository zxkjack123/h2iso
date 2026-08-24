"""Sample generation: Sobol sequences and Latin Hypercube Sampling.

Uses SALib for Sobol sensitivity analysis sample matrices and
scipy.stats.qmc for LHS. Both produce unit-hypercube samples that
are subsequently mapped through each Parameter's ``ppf``.
"""

from __future__ import annotations

import numpy as np

from h2iso.uq.distributions import Parameter


def _validate_parameters(parameters: list[Parameter]) -> None:
    if not parameters:
        raise ValueError("parameters list must not be empty")


def sobol_sample(
    parameters: list[Parameter],
    n_base: int = 128,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a Sobol sensitivity-analysis sample matrix.

    Uses SALib's ``sample.saltenberg`` (Sobol) strategy which produces
    ``N = n_base * (2 * K + 2)`` rows for *K* parameters.

    Returns
    -------
    ndarray of shape (N, K)
        Rows are parameter samples in the original (physical) space.
    """
    _validate_parameters(parameters)

    try:
        from SALib.sample import saltelli
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "SALib is required for Sobol sampling. Install with: pip install SALib"
        ) from exc

    K = len(parameters)
    problem = {
        "num_vars": K,
        "names": [p.name for p in parameters],
        "bounds": [[0.0, 1.0]] * K,
    }

    # SALib saltelli produces N = n_base * (2K + 2) unit-hypercube rows.
    # The Sobol sequence is deterministic; ``seed`` is mapped to
    # ``skip_values`` (number of initial points to skip) to provide
    # variation between runs with different seeds.
    skip_values = None
    if seed is not None:
        skip_values = int(seed) * 1000 + 100
    unit_samples = saltelli.sample(
        problem, n_base, calc_second_order=False, skip_values=skip_values
    )

    # Map each column through the corresponding parameter's ppf
    physical = np.empty_like(unit_samples)
    for j, param in enumerate(parameters):
        physical[:, j] = param.ppf(unit_samples[:, j])

    return physical


def lhs_sample(
    parameters: list[Parameter],
    n: int = 1000,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a Latin Hypercube Sample matrix.

    Uses ``scipy.stats.qmc.LatinHypercube`` to draw *n* samples in the
    unit hypercube, then maps each column through the parameter's ``ppf``.

    Returns
    -------
    ndarray of shape (n, K)
    """
    _validate_parameters(parameters)

    from scipy.stats import qmc

    K = len(parameters)
    sampler = qmc.LatinHypercube(d=K, seed=seed)
    unit_samples = sampler.random(n=n)

    physical = np.empty_like(unit_samples)
    for j, param in enumerate(parameters):
        physical[:, j] = param.ppf(unit_samples[:, j])

    return physical


def random_sample(
    parameters: list[Parameter],
    n: int = 1000,
    seed: int | None = None,
) -> np.ndarray:
    """Plain Monte-Carlo (iid) sampling — no stratification.

    Useful as a fallback or for large-N validation runs.
    """
    _validate_parameters(parameters)
    rng = np.random.default_rng(seed)
    return np.column_stack([p.sample(n, rng) for p in parameters])
