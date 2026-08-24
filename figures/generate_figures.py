#!/usr/bin/env python3
"""Generate publication-quality progress figures for h2iso project.

Four figures:
  1. CD2 column: top D₂ purity benchmark vs Wang 2022
  2. Pure-component normal boiling points vs molecular mass
  3. ISS-O three-column temperature profile vs Wang 2022
  4. Sobol total-order sensitivity indices (horizontal bar)

Output: figures/*.pdf + figures/*.png (300 dpi)
"""

import os
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# ── Global style ──────────────────────────────────────────────────
matplotlib.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 9.5,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "legend.fontsize": 8.5,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "grid.linestyle": (0, (1, 3)),
    }
)

OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Colour palette (colourblind-friendly Okabe-Ito subset)
C0 = "#0072B2"  # blue
C1 = "#D55E00"  # orange
C2 = "#009E73"  # teal-green
C3 = "#CC79A7"  # purple
GREY = "#555555"


def save(fig, name):
    for fmt in ("pdf", "png"):
        p = OUT_DIR / f"{name}.{fmt}"
        fig.savefig(str(p), dpi=300)
        print(f"  ✓ {p}")


# ═══════════════════════════════════════════════════════════════════
# Figure 1 — CD2 benchmark vs Wang 2022
# ═══════════════════════════════════════════════════════════════════
def fig1_cd2_benchmark():
    labels = ["Top D₂ Purity", "Bottom DT Enrichment"]
    h2iso_vals = [99.9966, 95.078]
    wang_vals = [99.9736, 94.006]

    x = np.arange(len(labels))
    width = 0.28

    fig, ax = plt.subplots(figsize=(6.0, 4.2))

    bars1 = ax.bar(
        x - width / 2,
        h2iso_vals,
        width,
        color=C0,
        edgecolor="white",
        linewidth=0.8,
        label="h2iso (CasADi MESH)",
    )
    bars2 = ax.bar(
        x + width / 2,
        wang_vals,
        width,
        color=C1,
        edgecolor="white",
        linewidth=0.8,
        label="Wang 2022 (Aspen Plus)",
    )

    # Value labels — shorter precision, placed inside/above
    for bar, val in zip(bars1, h2iso_vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val - 0.25,
            f"{val:.2f}%",
            ha="center",
            va="top",
            fontsize=8.5,
            fontweight="bold",
            color="white",
        )
    for bar, val in zip(bars2, wang_vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val - 0.25,
            f"{val:.2f}%",
            ha="center",
            va="top",
            fontsize=8.5,
            color="white",
        )

    # Delta callout — compact, beside the bars
    for i, (h, w) in enumerate(zip(h2iso_vals, wang_vals)):
        d = h - w
        ax.annotate(
            f"Δ = {d:+.3f} pp",
            xy=(x[i] + width / 2 + 0.04, w + 0.25),
            fontsize=8,
            color=GREY,
            ha="left",
            va="bottom",
        )

    ax.set_ylabel("Purity / Enrichment (%)")
    ax.set_title("CD2 Column: D₂/DT Separation Benchmark (75 stages, R=15)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(loc="lower right", framealpha=0.9)
    # Broaden y-range to avoid crowding; add "break" markers visually
    ax.set_ylim(92.5, 100.6)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    save(fig, "fig1_cd2_benchmark")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# Figure 2 — Normal boiling points vs molecular mass
# ═══════════════════════════════════════════════════════════════════
def fig2_boiling_points():
    species = ["H₂", "HD", "HT", "D₂", "DT", "T₂"]
    masses = [2.016, 3.022, 4.024, 4.028, 5.030, 6.032]
    nbp_h2iso = [20.27, 22.14, 22.92, 23.66, 24.98, 25.04]
    nbp_ref = [20.271, 22.143, 22.92, 23.661, 24.98, 25.04]

    fig, ax = plt.subplots(figsize=(6.0, 4.2))

    ax.plot(
        masses,
        nbp_h2iso,
        "o-",
        color=C0,
        markersize=9,
        markeredgecolor="white",
        markeredgewidth=0.8,
        label="h2iso (Souers + FH quantum corr.)",
    )
    ax.plot(
        masses,
        nbp_ref,
        "s--",
        color=C1,
        markersize=7.5,
        markeredgecolor="white",
        markeredgewidth=0.8,
        label="Reference (DIPPR 101 / NIST)",
    )

    # Light fill to show the small gap
    ax.fill_between(
        masses, nbp_h2iso, nbp_ref, alpha=0.12, color=C2, label=f"|Δ| < 0.3 K"
    )

    for sp, m, t in zip(species, masses, nbp_h2iso):
        ax.annotate(
            f"{sp}  {t:.2f} K",
            (m, t),
            textcoords="offset points",
            xytext=(9, -2),
            fontsize=8,
            ha="left",
            va="top",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.75, ec="none"),
        )

    ax.set_xlabel("Molecular Mass (amu)")
    ax.set_ylabel("Normal Boiling Point (K)")
    ax.set_title(
        "Hydrogen Isotopologue Boiling Points\nQuantum-corrected VLE Model Validation"
    )
    ax.legend(loc="lower right", framealpha=0.9, fontsize=8)
    ax.set_xlim(1.5, 6.8)
    ax.set_ylim(19.5, 25.8)
    fig.tight_layout()
    save(fig, "fig2_boiling_points")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# Figure 3 — ISS-O three-column temperature validation
# ═══════════════════════════════════════════════════════════════════
def fig3_isso_temperature():
    labels = ["CD1 Top", "CD1 Bot", "CD2 Top", "CD2 Bot", "CD3 Top", "CD3 Bot"]
    t_h2iso = [20.07, 21.81, 20.08, 23.25, 21.18, 24.54]
    t_wang = [20.06, 22.20, 20.08, 23.41, 21.56, 24.62]
    deltas = [h - w for h, w in zip(t_h2iso, t_wang)]
    markers_shapes = ["o", "s", "o", "s", "o", "s"]

    fig, ax = plt.subplots(figsize=(5.8, 5.8))

    t_min, t_max = 19.5, 25.5
    # y=x line
    ax.plot(
        [t_min, t_max],
        [t_min, t_max],
        "-",
        color="grey",
        lw=1.3,
        alpha=0.55,
        label="y = x (perfect match)",
    )
    # ±0.5 K envelope — more visible
    ax.fill_between(
        [t_min, t_max],
        [t_min - 0.5, t_max - 0.5],
        [t_min + 0.5, t_max + 0.5],
        alpha=0.12,
        color="grey",
        edgecolor="grey",
        linewidth=0.4,
        linestyle=":",
        label="± 0.5 K tolerance",
    )

    # Data points
    for i, (lb, h, w, d, mkr) in enumerate(
        zip(labels, t_h2iso, t_wang, deltas, markers_shapes)
    ):
        color = C0 if "Top" in lb else C2
        ax.scatter(
            w, h, c=color, marker=mkr, s=80, zorder=5, edgecolors="white", linewidth=0.7
        )

        # Annotation offset — compact, avoid overlap
        if lb == "CD1 Top":
            ox, oy = (12, -12)
        elif lb == "CD1 Bot":
            ox, oy = (12, -12)
        elif lb == "CD3 Bot":
            ox, oy = (10, -12)
        elif lb == "CD2 Top":
            ox, oy = (10, -12)
        elif lb == "CD3 Top":
            ox, oy = (10, -12)
        else:
            ox, oy = (10, -10)
        ax.annotate(
            f"{lb}  Δ={d:+.2f} K",
            (w, h),
            textcoords="offset points",
            xytext=(ox, oy),
            fontsize=7.5,
            ha="left",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.8, ec="none"),
        )

    ax.set_xlabel("Wang 2022 Temperature (K)")
    ax.set_ylabel("h2iso Temperature (K)")
    ax.set_title(
        "ISS-O Three-Column Temperature Validation  (CD1+CD2+CD3 vs Wang 2022)"
    )
    ax.set_xlim(t_min, t_max)
    ax.set_ylim(t_min, t_max)
    ax.set_aspect("equal")
    ax.legend(loc="lower right", framealpha=0.9, fontsize=7.5)

    # Inset — upper-left, compact; short labels to prevent internal text overlap
    ax_ins = ax.inset_axes((0.09, 0.58, 0.33, 0.34))
    ax_ins.set_facecolor("white")
    ax_ins.patch.set_alpha(0.95)
    for spine in ax_ins.spines.values():
        spine.set_edgecolor("#cccccc")
        spine.set_linewidth(0.5)
    colors_bar = [C0 if d <= 0 else C2 for d in deltas]
    bars = ax_ins.bar(
        range(len(labels)),
        deltas,
        color=colors_bar,
        edgecolor="white",
        lw=0.4,
    )
    ax_ins.axhline(0, color="grey", lw=0.8)
    ax_ins.set_xticks(range(len(labels)))
    # Short numeric + position labels (full names on main scatter annotations)
    ax_ins.set_xticklabels(
        ["1T", "1B", "2T", "2B", "3T", "3B"],
        fontsize=6.5,
    )
    # y-label on RIGHT side
    ax_ins.set_ylabel("ΔT (K)", fontsize=7, labelpad=1)
    ax_ins.yaxis.set_label_position("right")
    ax_ins.yaxis.tick_right()
    ax_ins.tick_params(axis="y", labelsize=6, pad=1)
    ax_ins.set_title("Per-location ΔT", fontsize=7.5, pad=3)

    # Pad y-limits so value labels never collide with x-axis tick labels
    y_lo, y_hi = min(deltas) - 0.15, max(deltas) + 0.12
    ax_ins.set_ylim(y_lo, y_hi)

    ax_ins.grid(axis="y", alpha=0.2)
    for bar, d in zip(bars, deltas):
        offset = 0.04 if d >= 0 else -0.04
        ypos = bar.get_height() + offset
        va = "bottom" if d >= 0 else "top"
        ax_ins.text(
            bar.get_x() + bar.get_width() / 2,
            ypos,
            f"{d:+.2f}",
            ha="center",
            va=va,
            fontsize=6,
            fontweight="bold",
            color=C0 if d <= 0 else C2,
        )

    fig.tight_layout(pad=1.5)
    save(fig, "fig3_isso_temperature")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
# Figure 4 — Sobol total-order sensitivity indices
# ═══════════════════════════════════════════════════════════════════
def fig4_sobol_sensitivity():
    qois = [
        "x_top[D₂]  (purity)",
        "x_bot[DT]  (enrichment)",
        "Q_condenser  (heat duty)",
        "T_top  (temperature)",
    ]
    parameters = ["z_D₂ (feed comp.)", "pressure", "reflux_ratio", "feed_flow"]

    # rows = QoI, cols = param  (total-order Sobol indices)
    st_data = np.array(
        [
            [0.9739, 1.57e-7, 9.464e-8, 4.077e-14],
            [0.9739, 1.57e-7, 9.464e-8, 2.296e-14],
            [0.0220, 2.896e-5, 0.6511, 0.1953],
            [0.6387, 0.8988, 6.227e-8, 4.737e-12],
        ]
    )

    # sqrt scale for better separation of small values
    st_display = np.sqrt(np.clip(st_data, 0, None))

    y = np.arange(len(qois))
    height = 0.19
    colors = [C0, C1, C2, C3]

    fig, ax = plt.subplots(figsize=(7.8, 4.8))

    for j, (param, color) in enumerate(zip(parameters, colors)):
        vals = st_display[:, j]
        bars = ax.barh(
            y + j * height,
            vals,
            height,
            label=param,
            color=color,
            edgecolor="white",
            linewidth=0.5,
        )
        for i, (bar, raw) in enumerate(zip(bars, st_data[:, j])):
            if raw > 0.01:
                txt = f" {raw:.3f}"
            elif raw > 1e-6:
                txt = f" {raw:.2e}"
            else:
                txt = ""
            if txt:
                ax.text(
                    bar.get_width() + 0.02,
                    bar.get_y() + bar.get_height() / 2,
                    txt,
                    va="center",
                    fontsize=6.8,
                    color=color,
                )

    ax.set_yticks(y + 1.5 * height)
    ax.set_yticklabels(qois, fontsize=9)
    ax.set_xlabel("√(Total-order Sobol′ index)   [sqrt transform]")
    ax.set_title(
        "CD2 Column: Global Sensitivity Analysis (Sobol′ Indices)\n"
        "UQ over z_D₂, pressure, reflux ratio, feed flow (N=32 base, 192 samples)"
    )
    ax.legend(loc="lower right", framealpha=0.9, ncol=2, fontsize=8)
    ax.set_xlim(0, ax.get_xlim()[1] * 1.40)
    ax.invert_yaxis()
    fig.tight_layout()
    save(fig, "fig4_sobol_sensitivity")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating h2iso progress figures …\n")
    fig1_cd2_benchmark()
    fig2_boiling_points()
    fig3_isso_temperature()
    fig4_sobol_sensitivity()
    pdfs = sorted(OUT_DIR.glob("*.pdf"))
    pngs = sorted(OUT_DIR.glob("*.png"))
    print(f"\nDone — {len(pdfs)} PDFs + {len(pngs)} PNGs in {OUT_DIR}/")
    for f in sorted(pdfs + pngs):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:45s} {size_kb:7.1f} KB")
