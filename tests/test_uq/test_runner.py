"""Tests for h2iso.uq.runner — sample evaluation."""

import numpy as np

from h2iso.mesh.column import ColumnResult, ColumnSpec
from h2iso.uq.qoi import qoi_default
from h2iso.uq.runner import run_samples


def _make_column_result(T_top=23.0, T_bot=25.0):
    """Minimal ColumnResult for testing."""
    N = 3
    x = np.zeros((N, 6))
    x[0, 3] = 0.99  # D2 at top
    x[-1, 4] = 0.95  # DT at bottom
    x = x / x.sum(axis=1, keepdims=True)
    return ColumnResult(
        T_profile=np.linspace(T_top, T_bot, N),
        x_profile=x,
        y_profile=x.copy(),
        L_profile=np.full(N, 100.0),
        V_profile=np.full(N, 120.0),
        condenser_duty=-400.0,
        reboiler_duty=410.0,
        convergence_info={"status": "Solve_Succeeded", "success": True},
    )


def _fake_build_fn(params: np.ndarray) -> ColumnSpec:
    """Build a dummy ColumnSpec from parameter vector [R, F]."""
    return ColumnSpec(
        n_stages=5,
        feed_stage=3,
        feed_flow=params[1] if len(params) > 1 else 80.0,
        feed_composition=np.array([0, 0, 0, 0.98, 0.02, 0]),
        pressure=90000.0,
        reflux_ratio=params[0],
        distillate_to_feed=0.979,
    )


def _fake_solve(config: ColumnSpec, **kwargs):
    """Fake solve that returns a fixed result — avoids CasADi."""
    return _make_column_result()


class TestRunSamples:
    def test_serial_basic(self):
        samples = np.array([[15, 80], [16, 82], [14, 78]])
        run_samples(
            samples,
            build_fn=_fake_build_fn,
            qoi_fn=qoi_default,
            parallel=1,
            solve_kwargs={"_fake": True},
        )

    def test_serial_with_mock(self, monkeypatch):
        """Patch _solve_config to avoid CasADi dependency."""
        import h2iso.uq.runner as runner_mod

        def mock_solve(config, **kwargs):
            return _make_column_result()

        monkeypatch.setattr(runner_mod, "_solve_config", mock_solve)

        samples = np.array([[15, 80], [16, 82], [14, 78]])
        summary = run_samples(
            samples,
            build_fn=_fake_build_fn,
            qoi_fn=qoi_default,
            parallel=1,
        )
        assert summary.n_total == 3
        assert summary.n_converged == 3
        assert summary.n_failed == 0
        assert summary.fail_rate == 0.0
        assert summary.qoi_matrix.shape == (3, 16)

    def test_failure_handling(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        call_count = [0]

        def mock_solve(config, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Simulated failure")
            return _make_column_result()

        monkeypatch.setattr(runner_mod, "_solve_config", mock_solve)

        samples = np.array([[15, 80], [16, 82], [14, 78]])
        summary = run_samples(
            samples,
            build_fn=_fake_build_fn,
            parallel=1,
        )
        assert summary.n_converged == 2
        assert summary.n_failed == 1
        assert summary.results[1].error is not None
        assert "Simulated failure" in summary.results[1].error

    def test_non_converged(self, monkeypatch):
        import h2iso.uq.runner as runner_mod
        from h2iso.flowsheet.solver import FlowsheetResult

        def mock_solve(config, **kwargs):
            return FlowsheetResult(
                streams={},
                converged=False,
                iterations=50,
                tear_residual=1.0,
            )

        monkeypatch.setattr(runner_mod, "_solve_config", mock_solve)

        samples = np.array([[15, 80]])
        summary = run_samples(
            samples,
            build_fn=_fake_build_fn,
            parallel=1,
        )
        assert summary.n_converged == 0
        assert summary.n_failed == 1

    def test_qoi_matrix_extraction(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        def mock_solve(config, **kwargs):
            return _make_column_result(T_top=23.0, T_bot=25.0)

        monkeypatch.setattr(runner_mod, "_solve_config", mock_solve)

        samples = np.array([[15, 80], [16, 82]])
        summary = run_samples(
            samples,
            build_fn=_fake_build_fn,
            parallel=1,
        )
        qmat = summary.qoi_matrix
        assert qmat.shape == (2, 16)
        # T_top should be 23.0 (index 2*6+2 = 14)
        assert np.allclose(qmat[:, 14], 23.0)
        # T_bot should be 25.0 (index 15)
        assert np.allclose(qmat[:, 15], 25.0)

    def test_sample_matrix_converged(self, monkeypatch):
        import h2iso.uq.runner as runner_mod

        def mock_solve(config, **kwargs):
            return _make_column_result()

        monkeypatch.setattr(runner_mod, "_solve_config", mock_solve)

        samples = np.array([[15, 80], [16, 82], [14, 78]])
        summary = run_samples(
            samples,
            build_fn=_fake_build_fn,
            parallel=1,
        )
        smat = summary.sample_matrix_converged
        assert smat.shape == (3, 2)
        np.testing.assert_array_equal(smat, samples)
