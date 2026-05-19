# Performance Baseline

This document records the performance baselines for h2iso key operations as
measured by `tests/benchmark/test_performance.py` (pytest-benchmark).

## Measurement Hardware (initial baseline)

- CPU: Intel Xeon W-2245 (8 cores, 16 threads) — dev workstation
- RAM: 128 GB DDR4
- OS: Ubuntu 24.04 LTS, Python 3.12.3
- Date: 2026

## Initial Baselines

| Benchmark | Group | Mean | StdDev | Notes |
|-----------|-------|------|--------|-------|
| `test_benchmark_bubble_pressure_1000x` | vle | 347 ms | 5 ms | 1000 random (T, x) VLE calls |
| `test_benchmark_cd2_75_plate` | mesh | 1.68 s | 0.17 s | CD2 column, 15→30→75 stage continuation |
| `test_benchmark_isso_three_column` | flowsheet | 16.9 s | 0.30 s | Wegstein, 3 continuation substeps, tol=1e-4 |

## Regression Policy

- **Warning** if mean increases > 25% vs prior recorded baseline
- **Failure** if mean increases > 50% vs prior recorded baseline (CI gate)
- Use relative comparison (vs last main-branch run) rather than absolute
  thresholds because CI-runner hardware varies.

## Running Benchmarks Locally

By default benchmarks are excluded from the regular test run (`addopts =
--benchmark-disable --ignore=tests/benchmark` in `pyproject.toml`). To run
them explicitly:

```bash
pytest tests/benchmark/ --benchmark-enable --override-ini="addopts="
```

To save a baseline for future comparison:

```bash
pytest tests/benchmark/ --benchmark-enable --override-ini="addopts=" \
    --benchmark-save=baseline_$(date +%Y%m%d)
```

## CI Integration

The `benchmark` job in `.github/workflows/ci.yml` runs only on `main` branch
pushes and uploads `.benchmarks/` as build artifacts. CI runner performance is
expected to differ from local baselines; the artifacts allow tracking trends
across commits.
