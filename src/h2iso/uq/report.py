"""Markdown report and CSV export for UQ studies."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from h2iso.uq.runner import RunSummary
from h2iso.uq.sobol import SobolResult


def _fmt(x: float, fmt: str = ".4g") -> str:
    if np.isnan(x):
        return "nan"
    if abs(x) < 1e-30:
        return "0"
    return format(x, fmt)


def save_csv(
    sample_matrix: np.ndarray,
    qoi_matrix: np.ndarray,
    parameter_names: list[str],
    qoi_names: list[str],
    path: str | Path,
) -> None:
    """Save samples + QoI as CSV (one row per converged sample)."""
    path = Path(path)
    header = ",".join(parameter_names + qoi_names)
    data = np.hstack([sample_matrix, qoi_matrix])
    lines = [header]
    for row in data:
        lines.append(",".join(_fmt(v) for v in row))
    path.write_text("\n".join(lines) + "\n")


def save_failures(
    summary: RunSummary,
    parameter_names: list[str],
    path: str | Path,
) -> None:
    """Save failed sample details as JSONL."""
    import json

    path = Path(path)
    lines = []
    for r in summary.results:
        if not r.converged:
            record = {
                "sample_index": r.sample_index,
                "parameter_values": {
                    parameter_names[j]: float(r.parameter_values[j])
                    for j in range(len(parameter_names))
                },
                "error": r.error,
            }
            lines.append(json.dumps(record, ensure_ascii=False))
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def generate_report(
    summary: RunSummary,
    parameter_names: list[str],
    qoi_names: list[str],
    sobol_result: SobolResult | None = None,
    title: str = "UQ Study Report",
) -> str:
    """Generate a Markdown report string."""
    lines: list[str] = []
    lines.append(f"# {title}\n")
    lines.append(f"- Total samples: **{summary.n_total}**")
    lines.append(f"- Converged: **{summary.n_converged}**")
    lines.append(f"- Failed: **{summary.n_failed}** ({summary.fail_rate:.1%})\n")

    # QoI statistics
    qmat = summary.qoi_matrix
    if qmat.size > 0:
        lines.append("## QoI Statistics\n")
        lines.append("| QoI | Mean | Std | Min | Max | 95% CI Low | 95% CI High |")
        lines.append("|-----|------|-----|-----|-----|------------|-------------|")
        mean = qmat.mean(axis=0)
        std = qmat.std(axis=0, ddof=1) if qmat.shape[0] > 1 else np.zeros(qmat.shape[1])
        lo = np.percentile(qmat, 2.5, axis=0)
        hi = np.percentile(qmat, 97.5, axis=0)
        for j, name in enumerate(qoi_names):
            lines.append(
                f"| {name} | {_fmt(mean[j])} | {_fmt(std[j])} | "
                f"{_fmt(qmat[:, j].min())} | {_fmt(qmat[:, j].max())} | "
                f"{_fmt(lo[j])} | {_fmt(hi[j])} |"
            )
        lines.append("")

    # Sobol indices
    if sobol_result is not None:
        lines.append("## Sobol Sensitivity Indices\n")
        lines.append("### Total-Order (ST)\n")
        lines.append("| Parameter | " + " | ".join(sobol_result.qoi_names) + " |")
        lines.append(
            "|-----------|" + "|".join(["---"] * len(sobol_result.qoi_names)) + "|"
        )
        for i, pname in enumerate(sobol_result.parameter_names):
            vals = " | ".join(
                _fmt(sobol_result.ST[i, j]) for j in range(len(sobol_result.qoi_names))
            )
            lines.append(f"| {pname} | {vals} |")
        lines.append("")

        lines.append("### First-Order (S1)\n")
        lines.append("| Parameter | " + " | ".join(sobol_result.qoi_names) + " |")
        lines.append(
            "|-----------|" + "|".join(["---"] * len(sobol_result.qoi_names)) + "|"
        )
        for i, pname in enumerate(sobol_result.parameter_names):
            vals = " | ".join(
                _fmt(sobol_result.S1[i, j]) for j in range(len(sobol_result.qoi_names))
            )
            lines.append(f"| {pname} | {vals} |")
        lines.append("")

    # Top-K parameters
    if sobol_result is not None and sobol_result.ST.size > 0:
        for j, qname in enumerate(sobol_result.qoi_names):
            top = sobol_result.top_k(
                k=min(5, len(sobol_result.parameter_names)), qoi_index=j
            )
            lines.append(f"**Top-5 for {qname} (ST):** {', '.join(top)}\n")

    return "\n".join(lines)


def save_report(
    summary: RunSummary,
    parameter_names: list[str],
    qoi_names: list[str],
    output_dir: str | Path,
    sobol_result: SobolResult | None = None,
    title: str = "UQ Study Report",
) -> Path:
    """Write report.md, samples.csv, and failures.jsonl to *output_dir*."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Report
    report_text = generate_report(
        summary, parameter_names, qoi_names, sobol_result, title
    )
    report_path = output_dir / "report.md"
    report_path.write_text(report_text)

    # CSV
    qmat = summary.qoi_matrix
    smat = summary.sample_matrix_converged
    if qmat.size > 0:
        save_csv(
            smat,
            qmat,
            parameter_names,
            qoi_names,
            output_dir / "samples.csv",
        )

    # Failures
    save_failures(summary, parameter_names, output_dir / "failures.jsonl")

    return report_path
