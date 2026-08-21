"""Plotting and statistical analysis script for CFEDR_3LC simulation results.

Generates a 4-panel comprehensive visualization figure:
- Subplot 1: I-ISS 所有进料与出料氚流量 (TEP Inflow & SDS/WDS/VDS/Secondary Outflows)
- Subplot 2: O-ISS 所有进料与出料氚流量 (TES/WDS/CPS Inflows & SDS/VDS/Secondary Outflows)
- Subplot 3: I-ISS 与 O-ISS 动态储氚滞留量 (Tritium Holdup in I-ISS & O-ISS)
- Subplot 4: SDS 储氚系统总滞留量 / 库存 (SDS Tritium Storage Inventory)
"""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def generate_plots():
    base_dir = Path(__file__).parent
    res_file = base_dir / "simulation_results_ssp_res.csv"

    if not res_file.exists():
        alt_file = base_dir / "simulation_results_ssp.csv"
        if alt_file.exists():
            res_file = alt_file
        else:
            print(f"[WARNING] Results file {res_file} does not exist. Run 'python run_simulation.py' first.")
            return

    df = pd.read_csv(res_file)

    # Plot settings
    plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans", "Arial"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(12, 14), dpi=300, sharex=True)

    # =========================================================================
    # Subplot 1: I-ISS 所有入料及出料氚流量
    # =========================================================================
    if "i_iss.from_TEP" in df.columns:
        ax1.plot(df["time"], df["i_iss.from_TEP"], label="进料: TEP -> I-ISS (排气净化氚流)", color="#1f77b4", linewidth=2.2)
    if "i_iss.to_SDS" in df.columns:
        ax1.plot(df["time"], df["i_iss.to_SDS"], label="出料: I-ISS -> SDS (高纯燃料产物)", color="#ff7f0e", linewidth=2.2)
    if "i_iss.to_WDS" in df.columns:
        ax1.plot(df["time"], df["i_iss.to_WDS"], label="出料: I-ISS -> WDS (脱氢尾气含氚)", color="#2ca02c", linestyle="--", linewidth=2.0)
    if "i_iss.to_VDS" in df.columns:
        ax1.plot(df["time"], df["i_iss.to_VDS"], label="泄漏: I-ISS -> VDS (通风除氚)", color="#d62728", linestyle=":", linewidth=1.8)
    if "i_iss.to_Secondary" in df.columns:
        ax1.plot(df["time"], df["i_iss.to_Secondary"], label="泄漏: I-ISS -> 二级包容", color="#9467bd", linestyle="-.", linewidth=1.8)

    ax1.set_title("1. CFEDR 3LC I-ISS 所有进料与出料氚流量动态响应 (I-ISS Tritium Flows)", fontsize=12, fontweight="bold", pad=6)
    ax1.set_ylabel("氚流率 (g/h) [symlog]", fontsize=10)
    ax1.set_yscale("symlog", linthresh=1e-4)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="center right", fontsize=9, framealpha=0.9)

    # =========================================================================
    # Subplot 2: O-ISS 所有入料及出料氚流量
    # =========================================================================
    if "o_iss.from_TES" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_TES"], label="进料: TES -> O-ISS (包层增殖提取氚)", color="#1f77b4", linewidth=2.2)
    if "o_iss.from_WDS" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_WDS"], label="进料: WDS -> O-ISS (水除氚浓缩回收)", color="#2ca02c", linestyle="--", linewidth=2.0)
    if "o_iss.from_CPS_PFC" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_CPS_PFC"], label="进料: CPS_PFC -> O-ISS (PFC 冷却剂净化)", color="#bcbd22", linestyle=":", linewidth=1.8)
    if "o_iss.from_CPS_BZ" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_CPS_BZ"], label="进料: CPS_BZ -> O-ISS (BZ 冷却剂净化)", color="#17becf", linestyle=":", linewidth=1.8)
    if "o_iss.to_SDS" in df.columns:
        ax2.plot(df["time"], df["o_iss.to_SDS"], label="出料: O-ISS -> SDS (高纯产氚提纯流)", color="#ff7f0e", linewidth=2.2)
    if "o_iss.to_VDS" in df.columns:
        ax2.plot(df["time"], df["o_iss.to_VDS"], label="泄漏: O-ISS -> VDS (通风除氚)", color="#d62728", linestyle=":", linewidth=1.8)
    if "o_iss.to_Secondary" in df.columns:
        ax2.plot(df["time"], df["o_iss.to_Secondary"], label="泄漏: O-ISS -> 二级包容", color="#9467bd", linestyle="-.", linewidth=1.8)

    ax2.set_title("2. CFEDR 3LC O-ISS 所有进料与出料氚流量动态响应 (O-ISS Tritium Flows)", fontsize=12, fontweight="bold", pad=6)
    ax2.set_ylabel("氚流率 (g/h) [symlog]", fontsize=10)
    ax2.set_yscale("symlog", linthresh=1e-4)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="center right", fontsize=9, framealpha=0.9)

    # =========================================================================
    # Subplot 3: I-ISS 与 O-ISS 动态储氚滞留量 (Tritium Holdup)
    # =========================================================================
    has_i_inv = "i_iss.inventory" in df.columns
    has_o_inv = "o_iss.inventory" in df.columns

    if has_i_inv:
        ax3.plot(df["time"], df["i_iss.inventory"], label="I-ISS 内部动态总储氚滞留量 (4塔+2平衡器)", color="#e377c2", linewidth=2.2)
    if has_o_inv:
        ax3.plot(df["time"], df["o_iss.inventory"], label="O-ISS 内部动态总储氚滞留量 (3塔+1平衡器)", color="#17becf", linewidth=2.2)
    if has_i_inv and has_o_inv:
        tot_iss = df["i_iss.inventory"] + df["o_iss.inventory"]
        ax3.plot(df["time"], tot_iss, label="全厂 ISS 总动态储氚滞留量 (I-ISS + O-ISS)", color="#8c564b", linestyle="--", linewidth=2.0)

    ax3.set_title("3. I-ISS 与 O-ISS 内部动态储氚滞留量 (Tritium Holdup in ISS)", fontsize=12, fontweight="bold", pad=6)
    ax3.set_ylabel("氚滞留量 (g)", fontsize=10)
    ax3.grid(True, linestyle=":", alpha=0.6)
    ax3.legend(loc="center right", fontsize=9, framealpha=0.9)

    # =========================================================================
    # Subplot 4: SDS 储氚系统总滞留量 (SDS Tritium Inventory)
    # =========================================================================
    if "sds.inventory" in df.columns:
        ax4.plot(df["time"], df["sds.inventory"], label="SDS 储氚库存 (SDS Tritium Storage Inventory)", color="#d62728", linewidth=2.4)

    ax4.set_title("4. CFEDR 3LC 全厂 SDS 储氚库存动态累积 (SDS Tritium Storage Inventory)", fontsize=12, fontweight="bold", pad=6)
    ax4.set_xlabel("仿真时间 (Time / h)", fontsize=10)
    ax4.set_ylabel("储氚库存 (g)", fontsize=10)
    ax4.grid(True, linestyle=":", alpha=0.6)
    ax4.legend(loc="upper left", fontsize=9, framealpha=0.9)

    plt.tight_layout()
    chart_path = base_dir / "comparison_chart.png"
    plt.savefig(chart_path, dpi=300)
    print(f"[INFO] Plot successfully saved to: {chart_path}")

    # Steady-state statistics
    ss = df[df["time"] >= (df["time"].max() * 0.8)]
    print("\n" + "=" * 76)
    print("      CFEDR 3LC 全厂燃料闭环 0-D 高保真动态仿真稳态数据表")
    print("=" * 76)
    print("【I-ISS 内燃料循环】:")
    if "i_iss.from_TEP" in df.columns:
        print(f"  - 进料 TEP 平均氚流量:           {ss['i_iss.from_TEP'].mean():.4f} g/h")
    if "i_iss.to_SDS" in df.columns:
        print(f"  - 出料 to SDS 产氚流率:          {ss['i_iss.to_SDS'].mean():.4f} g/h")
    if "i_iss.to_WDS" in df.columns:
        print(f"  - 出料 to WDS 废气氚流量:        {ss['i_iss.to_WDS'].mean():.4e} g/h")
    if has_i_inv:
        print(f"  - I-ISS 稳态储氚滞留量 (Holdup): {ss['i_iss.inventory'].mean():.4f} g")

    print("\n【O-ISS 外燃料循环】:")
    if "o_iss.from_TES" in df.columns:
        print(f"  - 进料 TES 平均氚流量:           {ss['o_iss.from_TES'].mean():.4f} g/h")
    if "o_iss.from_WDS" in df.columns:
        print(f"  - 进料 WDS 平均氚流量:           {ss['o_iss.from_WDS'].mean():.4f} g/h")
    if "o_iss.to_SDS" in df.columns:
        print(f"  - 出料 to SDS 产氚流率:          {ss['o_iss.to_SDS'].mean():.4f} g/h")
    if has_o_inv:
        print(f"  - O-ISS 稳态储氚滞留量 (Holdup): {ss['o_iss.inventory'].mean():.4f} g")

    if has_i_inv and has_o_inv:
        tot_iss_t = ss['i_iss.inventory'].mean() + ss['o_iss.inventory'].mean()
        print(f"\n【全厂 ISS (I+O) 总储氚滞留量】:    {tot_iss_t:.4f} g")

    if "sds.inventory" in df.columns:
        print(f"\n【全厂 SDS 储氚总盘存】 (5000h 末): {df['sds.inventory'].iloc[-1]:.2f} g")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    generate_plots()
