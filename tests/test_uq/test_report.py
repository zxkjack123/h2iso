"""Tests for h2iso.uq.report — Markdown and CSV output."""

import numpy as np
import pytest

from h2iso.uq.report import generate_report, save_csv, save_failures, save_report
from h2iso.uq.runner import RunResult, RunSummary
from h2iso.uq.sobol import SobolResult


@pytest.fixture
def summary():
    qoi_vals = np.array(
        [
            [0.99, 0.01, -400, 410, 23.0, 25.0],
            [0.98, 0.02, -410, 420, 23.2, 25.1],
            [0.995, 0.005, -390, 405, 22.9, 24.9],
        ]
    )
    param_vals = np.array(
        [
            [15.0, 80.0],
            [15.3, 80.5],
            [14.8, 79.5],
        ]
    )
    results = []
    for i in range(3):
        results.append(
            RunResult(
                sample_index=i,
                parameter_values=param_vals[i],
                qoi_values=qoi_vals[i],
                converged=True,
            )
        )
    # One failed
    results.append(
        RunResult(
            sample_index=3,
            parameter_values=np.array([16.0, 81.0]),
            qoi_values=None,
            converged=False,
            error="RuntimeError: IPOPT failed",
        )
    )
    return RunSummary(
        results=results,
        n_total=4,
        n_converged=3,
        n_failed=1,
        fail_rate=0.25,
    )


class TestSaveCSV:
    def test_basic(self, tmp_path):
        samples = np.array([[15, 80], [16, 82]])
        qois = np.array([[0.99, -400], [0.98, -410]])
        path = tmp_path / "out.csv"
        save_csv(samples, qois, ["R", "F"], ["x_D2", "Q_cond"], path)
        text = path.read_text()
        assert "R,F,x_D2,Q_cond" in text
        assert "15" in text
        lines = text.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows


class TestSaveFailures:
    def test_basic(self, summary, tmp_path):
        path = tmp_path / "failures.jsonl"
        save_failures(summary, ["R", "F"], path)
        text = path.read_text()
        assert "IPOPT failed" in text
        lines = text.strip().split("\n")
        assert len(lines) == 1  # only one failure


class TestGenerateReport:
    def test_basic(self, summary):
        report = generate_report(
            summary,
            ["R", "F"],
            ["x_D2", "x_DT", "Q_cond", "Q_reb", "T_top", "T_bot"],
        )
        assert "UQ Study Report" in report
        assert "Total samples: **4**" in report
        assert "Converged: **3**" in report
        assert "Failed: **1**" in report
        assert "x_D2" in report

    def test_with_sobol(self, summary):
        sobol = SobolResult(
            parameter_names=["R", "F"],
            qoi_names=["x_D2"],
            S1=np.array([[0.6], [0.1]]),
            ST=np.array([[0.7], [0.15]]),
            S1_conf=np.array([[0.05], [0.02]]),
            ST_conf=np.array([[0.06], [0.03]]),
        )
        report = generate_report(
            summary,
            ["R", "F"],
            ["x_D2"],
            sobol_result=sobol,
        )
        assert "Sobol" in report
        assert "R" in report
        assert "Top-5" in report


class TestSaveReport:
    def test_writes_files(self, summary, tmp_path):
        path = save_report(
            summary,
            ["R", "F"],
            ["x_D2", "x_DT", "Q_cond", "Q_reb", "T_top", "T_bot"],
            tmp_path,
        )
        assert path.exists()
        assert (tmp_path / "samples.csv").exists()
        assert (tmp_path / "failures.jsonl").exists()

    def test_creates_dir(self, summary, tmp_path):
        nested = tmp_path / "uq_run" / "output"
        save_report(summary, ["R", "F"], ["x_D2"], nested)
        assert (nested / "report.md").exists()
