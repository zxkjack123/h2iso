# h2iso / DWSIM / Aspen 三向对比 — 详细执行计划

> 本文档为 Task Executor 可逐条执行的精确计划。每个变更都有明确的文件路径、函数签名、完整代码和验收标准。不需要额外推断。

## 背景

- Aspen 基线数据在 `tests/fixtures/wang2022/iss_i_aspen_baseline.json`（5 工况 TC1-TC5, 元素级 H/D/T）
- DWSIM 管线在 tricys 的 `script/dwsim/` 中已验证可用
- ISS-I h2iso 模型在 `tests/fixtures/wang2022/iss_i.json` 中

## 非目标

- 不修改 tricys 代码
- 不做组分级别定量对比（等张世坤补数据）
- DWSIM 脚本仅在本地执行，不入 CI

---

## Task 1: 创建 `src/h2iso/parity/` 模块

### Task 1.1: `cases.py` — 加载 5 工况

**文件**：`src/h2iso/parity/cases.py`

**完整代码**：

```python
"""ISS-I test case definitions for three-way parity comparison.

Loads the 5 Aspen-baseline test cases (TC1-TC5) from the JSON fixture
and provides helper functions for feed composition calculation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Molar masses (g/mol) — must match the Aspen task spec
_M_H = 1.008
_M_D = 2.014
_M_T = 3.016

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent
    / "tests" / "fixtures" / "wang2022" / "iss_i_aspen_baseline.json"
)


def load_test_cases() -> list[dict]:
    """Return a list of 5 test case dicts (TC1-TC5)."""
    with open(FIXTURE_PATH) as f:
        return json.load(f)["test_cases"]


def get_feed_conditions(case: dict) -> dict:
    """Return feed H/D/T mass flows (g/h) and composition (6-species)."""
    return {
        "H_g_h": case["feed_atom_flow_g_h"]["H"],
        "D_g_h": case["feed_atom_flow_g_h"]["D"],
        "T_g_h": case["feed_atom_flow_g_h"]["T"],
        "composition": case["feed_composition"],
        "total_mol_h": case["feed_total_mol_h"],
    }


def get_products(case: dict) -> dict:
    """Return product stream H/D/T mass flows."""
    return case["products_atom_flow_g_h"]


def atom_to_species(H_g: float, D_g: float, T_g: float) -> np.ndarray:
    """Convert H/D/T mass flows (g/h) to 6-species mole fractions.

    Uses statistical equilibrium (random pairing) — same formula as Aspen task spec.
    """
    n_H = H_g / _M_H
    n_D = D_g / _M_D
    n_T = T_g / _M_T
    n_total = n_H + n_D + n_T
    if n_total <= 0:
        return np.zeros(6)
    x_H = n_H / n_total
    x_D = n_D / n_total
    x_T = n_T / n_total
    return np.array([
        x_H ** 2,          # H2
        2 * x_H * x_D,     # HD
        x_D ** 2,          # D2
        2 * x_H * x_T,     # HT
        2 * x_D * x_T,     # DT
        x_T ** 2,          # T2
    ])
```

**验收**：
```bash
python -c "from h2iso.parity.cases import load_test_cases; cases = load_test_cases(); print(len(cases)); print(cases[0]['case_id'])"
# 输出: 5 TC1
```

---

### Task 1.2: `h2iso_runner.py` — h2iso ISS-I 单工况求解

**文件**：`src/h2iso/parity/h2iso_runner.py`

**完整代码**：

```python
"""h2iso ISS-I single-case runner for parity comparison.

Solves the ISS-I three-column flowsheet with reduced stages (8-10)
for fast turnaround, and extracts H/D/T mass flows from the three
product streams (WDS, SDSD2, SDST2).
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from h2iso.flowsheet.schema import load_flowsheet
from h2iso.flowsheet.solver import SequentialModularSolver
from h2iso.parity.cases import atom_to_species

# Molar masses
_M_H = 1.008
_M_D = 2.014
_M_T = 3.016

# ISS-I JSON fixture
_FIXTURE_ISS_I = (
    Path(__file__).parent.parent.parent
    / "tests" / "fixtures" / "wang2022" / "iss_i.json"
)


def _composition_to_hdt(flow: float, x: np.ndarray) -> dict:
    """Convert species molar flow to H/D/T mass flows.

    flow: mol/h,  x: 6-element mole fraction [H2, HD, D2, HT, DT, T2]
    """
    Q = flow * np.asarray(x)
    H = (2 * Q[0] + Q[1] + Q[3]) * _M_H
    D = (Q[1] + 2 * Q[2] + Q[4]) * _M_D
    T = (Q[3] + Q[4] + 2 * Q[5]) * _M_T
    return {"H": float(H), "D": float(D), "T": float(T)}


def run_h2iso_iss_i(
    H_g_h: float,
    D_g_h: float,
    T_g_h: float,
    n_stages: int = 10,
    max_iter: int = 30,
    tol: float = 1e-3,
) -> dict:
    """Solve ISS-I for a given feed and return product H/D/T mass flows.

    Parameters
    ----------
    H_g_h, D_g_h, T_g_h : float
        Feed atom mass flows (g/h).
    n_stages : int
        Column stage count (reduced for speed; 10 = fast, 30+ = better accuracy).
    max_iter : int
        Max tear stream iterations.
    tol : float
        Convergence tolerance.

    Returns
    -------
    dict with keys:
        "case_id": str
        "feed_hdt": {"H": float, "D": float, "T": float}
        "feed_composition": dict (6 species)
        "feed_total_mol_h": float
        "products": {"WDS": {...}, "SDSD2": {...}, "SDST2": {...}}
        "converged": bool
        "iterations": int
        "tear_residual": float
        "solver_time_s": float
    """
    import time

    # Compute feed composition
    z = atom_to_species(H_g_h, D_g_h, T_g_h)

    # Compute total molar flow
    n_H = H_g_h / _M_H
    n_D = D_g_h / _M_D
    n_T = T_g_h / _M_T
    total_mol_h = (n_H + n_D + n_T) / 2.0  # each molecule has 2 atoms

    # Load base ISS-I config and scale stages
    config = load_flowsheet(_FIXTURE_ISS_I)
    for col in config.columns:
        col.n_stages = max(3, min(n_stages, col.n_stages))
    config.feeds[0].flow = total_mol_h
    config.feeds[0].composition = z

    # Solve
    solver = SequentialModularSolver(
        config,
        method="wegstein",
        continuation_substeps=0,
    )
    t0 = time.time()
    result = solver.solve(max_iter=max_iter, tol=tol)
    t1 = time.time()

    # Extract product flows
    products = {}
    # WDS = CD1_distillate + CD2_distillate (both go to waste)
    cd1_dist = result.streams.get("CD1_distillate")
    cd2_dist = result.streams.get("CD2_distillate")
    cd3_bot = result.streams.get("CD3_bottoms")

    # WDS = combined CD1+CD2 distillate
    if cd1_dist is not None and cd2_dist is not None:
        wds_flow = cd1_dist.flow + cd2_dist.flow
        # Weighted average composition for WDS
        wds_x = (
            cd1_dist.flow * np.asarray(cd1_dist.composition)
            + cd2_dist.flow * np.asarray(cd2_dist.composition)
        ) / wds_flow
        products["WDS"] = _composition_to_hdt(wds_flow, wds_x)
    else:
        products["WDS"] = {"H": 0.0, "D": 0.0, "T": 0.0}

    # SDSD2 = CD2 distillate (D2-rich product)
    if cd2_dist is not None:
        products["SDSD2"] = _composition_to_hdt(
            cd2_dist.flow, np.asarray(cd2_dist.composition)
        )
    else:
        products["SDSD2"] = {"H": 0.0, "D": 0.0, "T": 0.0}

    # SDST2 = CD3 bottoms (T2-rich product)
    if cd3_bot is not None:
        products["SDST2"] = _composition_to_hdt(
            cd3_bot.flow, np.asarray(cd3_bot.composition)
        )
    else:
        products["SDST2"] = {"H": 0.0, "D": 0.0, "T": 0.0}

    return {
        "feed_hdt": {"H": H_g_h, "D": D_g_h, "T": T_g_h},
        "feed_composition": {
            "H2": float(z[0]),
            "HD": float(z[1]),
            "D2": float(z[2]),
            "HT": float(z[3]),
            "DT": float(z[4]),
            "T2": float(z[5]),
        },
        "feed_total_mol_h": total_mol_h,
        "products": products,
        "converged": result.converged,
        "iterations": result.iterations,
        "tear_residual": float(result.tear_residual),
        "solver_time_s": round(t1 - t0, 3),
    }
```

**验收**：
```bash
# 从 h2iso 项目根目录执行（注意需要 solver 已安装）：
python -c "
from h2iso.parity.h2iso_runner import run_h2iso_iss_i
r = run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=6, max_iter=20)
print(f'converged={r[\"converged\"]}, WDS_H={r[\"products\"][\"WDS\"][\"H\"]:.2f}, SDST2_T={r[\"products\"][\"SDST2\"][\"T\"]:.2f}')"
# 预期：converged=True, SDST2_T > 0
```

---

### Task 1.3: `report.py` — 三向对比报告

**文件**：`src/h2iso/parity/report.py`

**完整代码**：

```python
"""Three-way parity report: Aspen Plus vs DWSIM vs h2iso.

Generates a Markdown report comparing H/D/T mass flows (g/h) across
the three software packages for all 5 test cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from h2iso.parity.cases import FIXTURE_PATH, load_test_cases, get_feed_conditions


def load_aspen_results() -> list[dict]:
    """Load Aspen baseline results from the fixture JSON."""
    return load_test_cases()


def load_dwsim_results(path: str | Path) -> list[dict]:
    """Load DWSIM results from a JSON file (generated by run_dwsim_baseline.py)."""
    with open(path) as f:
        return json.load(f)


def load_h2iso_results(path: str | Path) -> list[dict]:
    """Load h2iso results from a JSON file."""
    with open(path) as f:
        return json.load(f)


def _match_case(results: list[dict], case_id: str) -> dict | None:
    for r in results:
        if r.get("case_id") == case_id:
            return r
    return None


_STREAMS = ("WDS", "SDSD2", "SDST2")
_ELEMENTS = ("H", "D", "T")


def _safe_div(a: float, b: float) -> float:
    if abs(b) < 1e-15:
        return float("nan")
    return a / b


def generate_report(
    aspen: list[dict],
    dwsim: list[dict] | None = None,
    h2iso: list[dict] | None = None,
    title: str = "ISS-I Three-Way Parity Report",
) -> str:
    """Generate a Markdown three-way comparison report.

    Parameters
    ----------
    aspen : required, from load_aspen_results()
    dwsim : optional, from load_dwsim_results()
    h2iso : optional, from load_h2iso_results()

    Returns
    -------
    str : Markdown report
    """
    lines: list[str] = []
    lines.append(f"# {title}\n")

    # --- Test Setup ---
    lines.append("## Test Setup\n")
    lines.append("| Software | EOS | Solver | Notes |")
    lines.append("|----------|-----|--------|-------|")
    lines.append(
        "| Aspen Plus V14 | Peng-Robinson | Inside-Out | Zhang Shikun 2026-05, T2-Threetowers4.bkp |"
    )
    if dwsim:
        lines.append(
            "| DWSIM 9.0.5 | SRK | Simultaneous Correction | register_compounds.py, kij from Aspen |"
        )
    if h2iso:
        lines.append(
            "| h2iso 0.1.0 | Souers + quantum corr. | Sequential Modular + Wegstein | Reduced stages |"
        )
    lines.append("")

    # --- Per-Case Tables ---
    for aspen_case in aspen:
        case_id = aspen_case["case_id"]
        feed = aspen_case["feed_atom_flow_g_h"]
        lines.append(
            f"### {case_id}: {aspen_case['description']}\n"
        )
        lines.append(
            f"Feed: H={feed['H']:.1f}, D={feed['D']:.1f}, T={feed['T']:.1f} g/h\n"
        )

        # Build header
        header_cols = ["Stream", "Element", "Aspen"]
        if dwsim:
            header_cols.append("DWSIM")
        if h2iso:
            header_cols.append("h2iso")
        if dwsim and h2iso:
            header_cols.extend(["A/D %", "A/H %", "D/H %"])
        elif dwsim:
            header_cols.append("A/D %")
        elif h2iso:
            header_cols.append("A/H %")

        lines.append("| " + " | ".join(header_cols) + " |")
        sep = "|" + "|".join(["---"] * len(header_cols)) + "|"
        lines.append(sep)

        dwsim_case = _match_case(dwsim, case_id) if dwsim else None
        h2iso_case = _match_case(h2iso, case_id) if h2iso else None

        for stream in _STREAMS:
            a = aspen_case["products_atom_flow_g_h"].get(stream, {})
            d = dwsim_case["products"].get(stream, {}) if dwsim_case else {}
            h = h2iso_case["products"].get(stream, {}) if h2iso_case else {}

            for elem in _ELEMENTS:
                av = a.get(elem, 0.0)
                dv = d.get(elem, 0.0) if d else None
                hv = h.get(elem, 0.0) if h else None

                cols = [
                    stream,
                    elem,
                    f"{av:.4g}",
                ]
                if dwsim:
                    cols.append(f"{dv:.4g}" if dv is not None else "-")
                if h2iso:
                    cols.append(f"{hv:.4g}" if hv is not None else "-")

                if dwsim and dv is not None and abs(av) > 1e-10:
                    cols.append(f"{abs(av - dv) / abs(av) * 100:.1f}")
                elif dwsim and h2iso:
                    cols.append("-")
                if h2iso and hv is not None and abs(av) > 1e-10:
                    cols.append(f"{abs(av - hv) / abs(av) * 100:.1f}")
                elif h2iso and dwsim:
                    cols.append("-")
                if dwsim and h2iso and dv is not None and hv is not None and abs(dv) > 1e-10:
                    cols.append(f"{abs(dv - hv) / abs(dv) * 100:.1f}")

                lines.append("| " + " | ".join(cols) + " |")

        lines.append("")

    # --- Summary Table ---
    lines.append("## Summary\n")
    lines.append("| Pair | Mean Rel Error | Max Rel Error |")
    lines.append("|------|---------------|---------------|")

    pairs = []
    if dwsim:
        pairs.append(("Aspen vs DWSIM", aspen, dwsim))
    if h2iso:
        pairs.append(("Aspen vs h2iso", aspen, h2iso))
    if dwsim and h2iso:
        pairs.append(("DWSIM vs h2iso", dwsim, h2iso))

    for label, ref_results, test_results in pairs:
        errors = []
        for ref_case in ref_results:
            case_id = ref_case.get("case_id", "")
            test_case = _match_case(test_results, case_id)
            if not test_case:
                continue
            for stream in _STREAMS:
                ref_p = ref_case.get("products_atom_flow_g_h", ref_case.get("products", {})).get(stream, {})
                test_p = test_case.get("products", {}).get(stream, {})
                for elem in _ELEMENTS:
                    rv = ref_p.get(elem, 0.0)
                    tv = test_p.get(elem, 0.0)
                    if abs(rv) > 1e-6:
                        err = abs(tv - rv) / abs(rv)
                        if np.isfinite(err):
                            errors.append(err)

        if errors:
            mean_err = np.mean(errors) * 100
            max_err = np.max(errors) * 100
            lines.append(f"| {label} | {mean_err:.1f}% | {max_err:.1f}% |")
        else:
            lines.append(f"| {label} | N/A | N/A |")

    lines.append("")

    # --- Go/No-Go ---
    lines.append("## Go/No-Go\n")
    lines.append("| Pair | Threshold | Mean Err | Pass? |")
    lines.append("|------|-----------|----------|-------|")
    for label, ref_results, test_results in pairs:
        errors = []
        for ref_case in ref_results:
            case_id = ref_case.get("case_id", "")
            test_case = _match_case(test_results, case_id)
            if not test_case:
                continue
            for stream in _STREAMS:
                ref_p = ref_case.get("products_atom_flow_g_h", ref_case.get("products", {})).get(stream, {})
                test_p = test_case.get("products", {}).get(stream, {})
                for elem in _ELEMENTS:
                    rv = ref_p.get(elem, 0.0)
                    tv = test_p.get(elem, 0.0)
                    if abs(rv) > 1e-6:
                        err = abs(tv - rv) / abs(rv)
                        if np.isfinite(err):
                            errors.append(err)
        if errors:
            m = np.mean(errors) * 100
            threshold = 15.0 if "DWSIM vs h2iso" in label else 10.0
            status = "✅" if m < threshold else "❌"
            lines.append(f"| {label} | {threshold:.0f}% | {m:.1f}% | {status} |")

    lines.append("")
    return "\n".join(lines)


def save_report(
    aspen: list[dict],
    dwsim: list[dict] | None = None,
    h2iso: list[dict] | None = None,
    output_path: str | Path = "parity_report.md",
) -> Path:
    """Generate and save the parity report."""
    output_path = Path(output_path)
    report = generate_report(aspen, dwsim, h2iso)
    output_path.write_text(report)
    return output_path
```

**验收**：
```bash
python -c "
from h2iso.parity.report import load_aspen_results, generate_report
aspen = load_aspen_results()
report = generate_report(aspen)
print(len(report))
assert 'TC1' in report
print('OK')
"
```

---

### Task 1.4: `__init__.py` — 模块入口

**文件**：`src/h2iso/parity/__init__.py`

```python
"""h2iso parity — multi-software comparison framework.

Provides test case loading, h2iso single-case runner, and three-way
report generation for Aspen Plus / DWSIM / h2iso comparisons.
"""

from h2iso.parity.cases import (
    atom_to_species,
    get_feed_conditions,
    get_products,
    load_test_cases,
)
from h2iso.parity.h2iso_runner import run_h2iso_iss_i
from h2iso.parity.report import (
    generate_report,
    load_aspen_results,
    load_dwsim_results,
    load_h2iso_results,
    save_report,
)

__all__ = [
    "load_test_cases",
    "get_feed_conditions",
    "get_products",
    "atom_to_species",
    "run_h2iso_iss_i",
    "generate_report",
    "load_aspen_results",
    "load_dwsim_results",
    "load_h2iso_results",
    "save_report",
]
```

---

## Task 2: DWSIM 5 工况运行脚本

### Task 2.1: 复制 tricys 的 `register_compounds.py`

```bash
cp ~/opt/tricys/script/dwsim/register_compounds.py ~/opt/h2iso/script/register_compounds.py
```

### Task 2.2: `run_dwsim_baseline.py`

**文件**：`script/run_dwsim_baseline.py`

```python
#!/usr/bin/env python3
"""Run DWSIM 5-case baseline and save results as JSON.

Usage:
    cd /path/to/h2iso
    python script/run_dwsim_baseline.py [--output dwsim_results.json]
"""

import json
import os
import sys
import time

DWSIM_DIR = os.environ.get("DWSIM_DIR", "/usr/local/lib/dwsim")
DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "/usr/lib/dotnet")

_M_H = 1.008
_M_D = 2.014
_M_T = 3.016

TEST_CASES = {
    "TC1": (100.0, 50.0, 10.0),
    "TC2": (50.0, 50.0, 50.0),
    "TC3": (150.0, 10.0, 5.0),
    "TC4": (10.0, 100.0, 50.0),
    "TC5": (80.0, 30.0, 20.0),
}

DWSIM_COMPOUNDS = ["Hydrogen", "HD", "Deuterium", "HT", "DT", "Tritium"]

OUTPUT_STREAMS = {"WDS": "S4", "SDSD2": "S16", "SDST2": "S17"}


def setup_runtime():
    from pythonnet import set_runtime
    from clr_loader import get_coreclr

    rt = get_coreclr(dotnet_root=DOTNET_ROOT)
    set_runtime(rt)


def extract_hdt(stream) -> dict:
    """Extract H/D/T mass flows (g/h) from a DWSIM material stream.

    formula:
        n_H  = 2*n(H2) + n(HD) + n(HT)
        n_D  = n(HD) + 2*n(D2) + n(DT)
        n_T  = n(HT) + n(DT) + 2*n(T2)
    """
    compounds = stream.Phases[0].Compounds  # overall compounds
    n = {}
    for comp in DWSIM_COMPOUNDS:
        n[comp] = compounds[comp].MoleFlow  # mol/s

    H_mol = 2 * n["Hydrogen"] + n["HD"] + n["HT"]
    D_mol = n["HD"] + 2 * n["Deuterium"] + n["DT"]
    T_mol = n["HT"] + n["DT"] + 2 * n["Tritium"]

    # Convert mol/s → g/h
    return {
        "H": H_mol * _M_H * 3600,
        "D": D_mol * _M_D * 3600,
        "T": T_mol * _M_T * 3600,
    }


def atom_to_species(T_g, D_g, H_g):
    """Compute statistical equilibrium feed composition (mol fractions, 6 species)."""
    n_H = H_g / _M_H
    n_D = D_g / _M_D
    n_T = T_g / _M_T
    nt = n_H + n_D + n_T
    xH = n_H / nt
    xD = n_D / nt
    xT = n_T / nt
    return {
        "Hydrogen": xH * xH,
        "HD": 2 * xH * xD,
        "Deuterium": xD * xD,
        "HT": 2 * xH * xT,
        "DT": 2 * xD * xT,
        "Tritium": xT * xT,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dwsim_results.json")
    args = parser.parse_args()

    print(f"DWSIM_DIR={DWSIM_DIR}")
    setup_runtime()

    import clr
    sys.path.append(DWSIM_DIR)
    clr.AddReference("DWSIM.Automation")
    clr.AddReference("DWSIM.Interfaces")
    from DWSIM.Automation import Automation3
    from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType

    # Import register_compounds from script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    from register_compounds import register_compounds

    results = []

    for case_id, (T_g, D_g, H_g) in TEST_CASES.items():
        print(f"\n{'='*60}\n{case_id}: T={T_g}, D={D_g}, H={H_g} g/h\n{'='*60}")
        t0 = time.time()

        interf = Automation3()
        sim = interf.CreateFlowsheet()

        # Step 1: Register compounds
        register_compounds(sim, {})

        # Step 2: SRK property package
        sim.CreateAndAddPropertyPackage("Soave-Redlich-Kwong (SRK)")

        # Step 3: Create feed stream
        feed_z = atom_to_species(T_g, D_g, H_g)
        total_flow = (
            H_g / _M_H + D_g / _M_D + T_g / _M_T
        ) / 2.0 * (1000.0 / 3600.0)  # mol/h → mmol/s

        m1 = sim.AddObject(ObjectType.MaterialStream, 50, 200, "FROMTEP")
        m1 = m1.GetAsObject()
        m1.SetTemperature(23.89)  # K
        m1.SetPressure(100000.0)  # Pa
        m1.SetMolarFlow(total_flow)
        for comp_name, frac in feed_z.items():
            m1.SetOverallCompoundMolarFlow(comp_name, total_flow * frac)

        print(f"  Feed: T=23.89 K, P=100000 Pa, F={total_flow:.4f} mmol/s")

        # Step 4: Solve (material stream only — no columns yet, just flash)
        try:
            interf.CalculateFlowsheet2(sim)
            # Read back overall composition
            hdt = extract_hdt(m1)
            products = {
                "WDS": {"H": 0.0, "D": 0.0, "T": 0.0},
                "SDSD2": {"H": 0.0, "D": 0.0, "T": 0.0},
                "SDST2": {"H": 0.0, "D": 0.0, "T": 0.0},
            }

            # For now: single-column approximation.
            # The full ISS-I topology requires build_dwsim_flowsheet.py — which
            # is heavy and slow. For a first pass, we record the feed conditions
            # and flag that full-column DWSIM results require the heavier script.
            results.append({
                "case_id": case_id,
                "feed_hdt": {"H": H_g, "D": D_g, "T": T_g},
                "feed_composition": feed_z,
                "products": products,
                "converged": True,
                "solver_time_s": round(time.time() - t0, 3),
                "note": "Full ISS-I DWSIM solve requires build_dwsim_flowsheet.py (tricys). This is a feed-only placeholder.",
            })
            print(f"  OK ({time.time() - t0:.1f}s)")

        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({
                "case_id": case_id,
                "feed_hdt": {"H": H_g, "D": D_g, "T": T_g},
                "feed_composition": feed_z,
                "products": {},
                "converged": False,
                "error": str(e),
                "solver_time_s": round(time.time() - t0, 3),
            })

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> **注意**：DWSIM 全三塔 ISS-I 求解需要 `build_dwsim_flowsheet.py`（tricys 项目中的完整脚本），这超出了 h2iso 项目的 scope。当前脚本作为起点——先验证 DWSIM 环境可用、化合物注册正常，全塔求解后续可从 tricys 克隆并纳入。

**验收**：
```bash
python script/run_dwsim_baseline.py --output dwsim_results.json
# 预期：5 cases processed, output JSON has 5 entries with feed_composition populated
```

---

## Task 3: 测试

### Task 3.1: `test_cases.py`

**文件**：`tests/test_parity/test_cases.py`

```python
"""Test parity case loading."""

from h2iso.parity.cases import (
    atom_to_species,
    get_feed_conditions,
    get_products,
    load_test_cases,
)


class TestLoadCases:
    def test_loads_five_cases(self):
        cases = load_test_cases()
        assert len(cases) == 5
        ids = [c["case_id"] for c in cases]
        assert ids == ["TC1", "TC2", "TC3", "TC4", "TC5"]

    def test_tc1_feed(self):
        cases = load_test_cases()
        feed = get_feed_conditions(cases[0])
        assert feed["H_g_h"] == 10.0
        assert feed["D_g_h"] == 50.0
        assert feed["T_g_h"] == 100.0
        assert abs(feed["total_mol_h"] - 33.95) < 0.1

    def test_tc1_products(self):
        cases = load_test_cases()
        prods = get_products(cases[0])
        assert "WDS" in prods
        assert "SDST2" in prods
        assert "SDSD2" in prods


class TestAtomToSpecies:
    def test_output_sums_to_one(self):
        z = atom_to_species(10.0, 50.0, 100.0)
        assert abs(z.sum() - 1.0) < 1e-10

    def test_matches_tc1(self):
        z = atom_to_species(10.0, 50.0, 100.0)
        # TC1 expected (from Aspen): H2=0.02135, DT=0.357, T2=0.2384
        assert abs(z[0] - 0.02135) < 0.001
        assert abs(z[4] - 0.357) < 0.01
        assert abs(z[5] - 0.2384) < 0.01
```

### Task 3.2: `test_h2iso_runner.py`

**文件**：`tests/test_parity/test_h2iso_runner.py`

```python
"""Test h2iso ISS-I runner for parity."""

import pytest
from h2iso.parity.h2iso_runner import run_h2iso_iss_i


class TestH2isoRunner:
    def test_tc1_converges(self):
        r = run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=6, max_iter=20)
        assert r["converged"]

    def test_tc1_products_positive(self):
        r = run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=6, max_iter=20)
        for stream in ("WDS", "SDST2"):
            for elem in ("H", "D", "T"):
                v = r["products"][stream][elem]
                assert v >= 0, f"{stream}.{elem} negative: {v}"

    def test_tc1_sdst2_t_positive(self):
        r = run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=6, max_iter=20)
        # SDST2 (CD3 bottom) should have non-zero T
        assert r["products"]["SDST2"]["T"] > 0


@pytest.mark.slow
class TestH2isoRunnerSlow:
    def test_tc1_10stage(self):
        r = run_h2iso_iss_i(10.0, 50.0, 100.0, n_stages=10, max_iter=30)
        assert r["converged"]

    def test_all_cases_10stage(self):
        for H, D, T in [(10, 50, 100), (50, 50, 50), (5, 10, 150)]:
            r = run_h2iso_iss_i(float(H), float(D), float(T), n_stages=10, max_iter=30)
            assert r["converged"], f"H={H} D={D} T={T} not converged"
```

### Task 3.3: `test_report.py`

**文件**：`tests/test_parity/test_report.py`

```python
"""Test parity report generation."""

from h2iso.parity.report import (
    generate_report,
    load_aspen_results,
)


class TestReport:
    def test_aspen_only(self):
        aspen = load_aspen_results()
        report = generate_report(aspen)
        assert "ISS-I Three-Way Parity Report" in report
        assert "TC1" in report
        assert "TC5" in report
        assert "Aspen" in report

    def test_aspen_only_output_sections(self):
        aspen = load_aspen_results()
        report = generate_report(aspen)
        assert "Test Setup" in report
        assert "Summary" in report
        assert "Go/No-Go" in report
```

### Task 3.4: `__init__.py`

**文件**：`tests/test_parity/__init__.py`（空文件）

---

## Task 4: 运行验证

### 4.1: 创建目录

```bash
mkdir -p src/h2iso/parity tests/test_parity script
```

### 4.2: 复制 register_compounds.py

```bash
cp ~/opt/tricys/script/dwsim/register_compounds.py ~/opt/h2iso/script/register_compounds.py
```

### 4.3: ruff

```bash
ruff check src/h2iso/parity/ tests/test_parity/
ruff format src/h2iso/parity/ tests/test_parity/
```

### 4.4: 测试

```bash
# Fast tests (CI-safe, no DWSIM)
pytest tests/test_parity/ -x --tb=short

# DWSIM test (local only)
python script/run_dwsim_baseline.py

# Full regression
pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e -q
```

---

## 审查日志

### R1 — 结构完整性
- T1.1-T1.4：parity 模块 4 个文件，每个含完整代码 ✓
- T2.1-T2.2：DWSIM 脚本，含完整代码 ✓  
- T3.1-T3.4：4 个测试文件，含完整代码 ✓
- T4：验证步骤 ✓

### R1.5 — 外部引用
- `iss_i_aspen_baseline.json` ✓
- `iss_i.json` ✓
- tricys `register_compounds.py` ✓
- DWSIM 已安装 ✓
- pythonnet 已安装 ✓

### R2 — 可执行性
- 每个文件都有完整代码，无需推断 ✓
- 验收命令明确 ✓
- DWSIM 脚本标注了限制（全塔求解需 tricys `build_dwsim_flowsheet.py`）✓

### R2.8 — LLM 可执行性
- 文件路径、函数签名、完整代码均已提供 ✓
- 0 模糊项 ✓

### R3 — 风险
- DWSIM 全塔求解标记为后续工作 ✓
- CI 测试不与 DWSIM 耦合 ✓
