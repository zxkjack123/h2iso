"""Persistent regression: importing h2iso must not eagerly require CasADi.

CasADi is an *optional* dependency (``h2iso[solver]``).  The CI
``lint-and-fast-test`` job installs ``.[dev]`` only, so ``import h2iso`` must
succeed when CasADi is absent.  This module blocks CasADi via a
``sys.meta_path`` finder inside a subprocess and asserts that:

1. ``import h2iso`` succeeds and leaves ``casadi`` out of ``sys.modules``;
2. ``h2iso.mesh`` / ``h2iso.flowsheet.solver`` import without CasADi;
3. actually *calling* the solver raises an actionable ``ImportError`` that
   mentions ``h2iso[solver]`` — i.e. the failure is lazy, not silent.

No network access is required.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

_BLOCKER = textwrap.dedent(
    """
    import sys

    class _CasadiBlocker:
        def find_spec(self, name, path=None, target=None):
            if name == "casadi" or name.startswith("casadi."):
                raise ModuleNotFoundError("No module named 'casadi' (blocked by test)")
            return None

    sys.meta_path.insert(0, _CasadiBlocker())
    """
)


def _run_blocked(snippet: str) -> subprocess.CompletedProcess:
    """Run ``snippet`` in a fresh interpreter with CasADi blocked."""
    code = _BLOCKER + "\n" + textwrap.dedent(snippet)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_import_h2iso_without_casadi():
    proc = _run_blocked(
        """
        import h2iso
        assert "casadi" not in sys.modules, (
            "casadi was imported eagerly by `import h2iso`"
        )
        assert h2iso.SPECIES
        print("ok")
        """
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_mesh_and_flowsheet_import_without_casadi():
    proc = _run_blocked(
        """
        import h2iso.mesh.column
        import h2iso.mesh.enthalpy
        import h2iso.mesh.stage
        from h2iso.flowsheet.solver import SequentialModularSolver

        assert "casadi" not in sys.modules, (
            "casadi was imported eagerly by the mesh/flowsheet imports"
        )
        assert SequentialModularSolver is not None
        print("ok")
        """
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_solver_call_raises_import_error_without_casadi():
    proc = _run_blocked(
        """
        import numpy as np

        from h2iso.mesh.column import Column, ColumnSpec

        spec = ColumnSpec(
            n_stages=5,
            feed_stage=3,
            feed_flow=80.0,
            feed_composition=np.array([0.0, 0.0, 0.0, 0.98, 0.02, 0.0]),
            pressure=90000.0,
            reflux_ratio=10.0,
            distillate_to_feed=0.979,
        )
        try:
            Column(spec).solve()
        except ImportError as exc:
            message = str(exc)
            assert "h2iso[solver]" in message, (
                f"ImportError message is not actionable: {message!r}"
            )
            print("raised:" + message)
        else:
            raise AssertionError("expected ImportError when casadi is unavailable")
        """
    )
    assert proc.returncode == 0, proc.stderr
    assert "raised:" in proc.stdout
