"""Tests for CLI flowsheet subcommand."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "wang2022" / "wang2022_isso.json"
)


class TestCLIFlowsheetHelp:
    """Test flowsheet --help."""

    def test_flowsheet_help(self):
        """h2iso flowsheet --help exits 0 and shows usage."""
        result = subprocess.run(
            [sys.executable, "-m", "h2iso", "flowsheet", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--config" in result.stdout
        assert "--max-iter" in result.stdout
        assert "--tol" in result.stdout

    def test_h2iso_help_lists_flowsheet(self):
        """h2iso --help lists flowsheet subcommand."""
        result = subprocess.run(
            [sys.executable, "-m", "h2iso", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "flowsheet" in result.stdout


class TestCLIFlowsheetSolve:
    """Test flowsheet solve end-to-end."""

    def test_solve_isso(self, tmp_path):
        """h2iso flowsheet --config isso.json produces summary.json."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "h2iso",
                "flowsheet",
                "--config",
                str(FIXTURE_PATH),
                "--output",
                str(tmp_path),
                "--max-iter",
                "50",
                "--tol",
                "1e-4",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "CONVERGED" in result.stdout

        # Check summary.json exists
        summary_path = tmp_path / "summary.json"
        assert summary_path.exists()

        with open(summary_path) as f:
            summary = json.load(f)

        assert summary["converged"] is True
        assert summary["iterations"] <= 50
        assert "streams" in summary
        assert len(summary["streams"]) > 0

    def test_solve_missing_config(self):
        """CLI errors on missing config file."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "h2iso",
                "flowsheet",
                "--config",
                "/nonexistent.json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
