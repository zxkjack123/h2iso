"""Persistent regression: CI configuration invariants.

Parses ``.github/workflows/ci.yml`` and ``constraints/`` with a small,
self-contained YAML-subset reader (no third-party ``yaml`` dependency, no
network) and asserts that the CI determinism fixes stay in place:

1. the ``test`` job maps each Python version to its own constraints file;
2. the ``test-solver`` job (3.11) uses the 3.11 constraints file;
3. ``benchmark`` and ``e2e-modelica`` install the ``solver`` extra;
4. the OpenModelica apt key comes from the verified URL, not the dead ones;
5. the ``lint-and-fast-test`` job pins its dependencies for determinism;
6. the ``e2e-modelica`` job installs the Modelica Standard Library (apt ``omc``
   alone does not ship it) and verifies it loaded.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CONSTRAINTS_DIR = REPO_ROOT / "constraints"

VERIFIED_OM_KEY_URL = "https://build.openmodelica.org/apt/openmodelica.asc"
DEAD_OM_KEY_URLS = (
    "deb.openmodelica.org.gpg.key",
    "build.openmodelica.org.key",
)


def _job_block(text: str, job_name: str) -> str:
    """Return the YAML block of a top-level (4-space indented) job."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^    {re.escape(job_name)}:\s*$", line):
            start = i
            break
    if start is None:
        raise AssertionError(f"job {job_name!r} not found in ci.yml")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^    [A-Za-z0-9_-]+:\s*$", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def _assign(mapping: dict[str, str], scalar: str) -> None:
    if ":" not in scalar:
        return
    key, _, value = scalar.partition(":")
    mapping[key.strip()] = value.strip().strip('"').strip("'")


def _list_of_mappings(block: str, key: str) -> list[dict[str, str]]:
    """Parse a YAML sequence-of-mappings nested under ``key:``."""
    lines = block.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(key)}:\s*$", line):
            start = i
            break
    if start is None:
        raise AssertionError(f"key {key!r} not found in block")

    key_indent = len(lines[start]) - len(lines[start].lstrip())
    item_indent: int | None = None
    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in lines[start + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= key_indent:
            break
        dash = re.match(r"^(\s*)-\s*(.*)$", line)
        if dash and (item_indent is None or len(dash.group(1)) == item_indent):
            item_indent = len(dash.group(1))
            current = {}
            items.append(current)
            if dash.group(2).strip():
                _assign(current, dash.group(2).strip())
        elif current is not None:
            _assign(current, line.strip())

    return items


def _ci_text() -> str:
    return CI_YML.read_text(encoding="utf-8")


def test_test_job_maps_each_python_to_its_own_constraints():
    block = _job_block(_ci_text(), "test")
    entries = _list_of_mappings(block, "include")
    mapping = {e.get("python-version"): e.get("constraints") for e in entries}

    expected = {
        "3.9": "constraints/py3.9.txt",
        "3.11": "constraints/py3.11.txt",
        "3.12": "constraints/ci-3.12.txt",
    }
    assert mapping == expected, f"matrix include mapping mismatch: {mapping!r}"
    for path in expected.values():
        assert (REPO_ROOT / path).is_file(), f"missing constraints file: {path}"


def test_test_solver_job_uses_py311_constraints():
    block = _job_block(_ci_text(), "test-solver")

    assert re.search(r'python-version:\s*"3\.11"', block), (
        "test-solver must run on Python 3.11"
    )
    assert "constraints/py3.11.txt" in block, (
        "test-solver (3.11) must use constraints/py3.11.txt"
    )
    assert "constraints/ci-3.12.txt" not in block, (
        "test-solver (3.11) must not reuse the 3.12 constraints file"
    )


def test_benchmark_and_e2e_install_solver_extra():
    for job in ("benchmark", "e2e-modelica"):
        block = _job_block(_ci_text(), job)
        installs = [
            ln for ln in block.splitlines() if "pip install" in ln and " -e " in ln
        ]
        assert installs, f"no editable install found in job {job!r}"
        assert any("dev,solver" in ln for ln in installs), (
            f"job {job!r} must install the solver extra; found: {installs!r}"
        )


def test_benchmark_and_e2e_pin_dependencies():
    """benchmark/e2e are Python 3.12, so they must consume the 3.12 constraints.

    Without ``-c`` these jobs float CasADi to the latest release, which breaks
    the three-leg "unified CasADi 3.7.2" guarantee (D2 + D1 refinement).
    """
    for job in ("benchmark", "e2e-modelica"):
        block = _job_block(_ci_text(), job)
        installs = [
            ln for ln in block.splitlines() if "pip install" in ln and " -e " in ln
        ]
        assert installs, f"no editable install found in job {job!r}"
        assert any("-c constraints/ci-3.12.txt" in ln for ln in installs), (
            f"job {job!r} must pin dependencies with `-c constraints/ci-3.12.txt` "
            f"so its casadi matches the unified 3.7.2; found: {installs!r}"
        )


def test_openmodelica_key_uses_verified_url():
    block = _job_block(_ci_text(), "e2e-modelica")

    assert VERIFIED_OM_KEY_URL in block, (
        f"e2e-modelica must fetch the OpenModelica key from {VERIFIED_OM_KEY_URL}"
    )
    for dead in DEAD_OM_KEY_URLS:
        assert dead not in block, f"dead OpenModelica key URL still referenced: {dead}"


def test_lint_job_pins_dependencies_for_determinism():
    block = _job_block(_ci_text(), "lint-and-fast-test")

    assert "constraints/ci-3.12.txt" in block, (
        "lint-and-fast-test must consume constraints/ci-3.12.txt so its ruff "
        "version matches the pinned legs"
    )


def test_e2e_modelica_installs_modelica_standard_library():
    """PM4012 expansion: e2e-modelica must install the MSL, not just ``omc``.

    The apt ``omc`` package ships the compiler but *not* the Modelica Standard
    Library.  Without it every generated record that extends
    ``Modelica.Icons.Record`` fails to compile (CI: ``Error: Failed to load
    package Modelica`` / ``Base class Modelica.Icons.Record not found``).
    The install must additionally be verified loudly (``loadModel(Modelica)``
    returning ``true``) so a failed download fails the job instead of being
    silently skipped.
    """
    block = _job_block(_ci_text(), "e2e-modelica")

    assert "installPackage(Modelica)" in block, (
        "e2e-modelica must install the Modelica Standard Library via omc "
        "installPackage(Modelica) — apt omc alone does not ship the MSL"
    )
    assert re.search(r"loadModel\(Modelica\)", block), (
        "e2e-modelica must verify the MSL loaded (loadModel(Modelica)) so a "
        "failed install fails the job loudly rather than silently"
    )
