"""Plotting and statistical analysis script for Modelica 0-D simulation results.

Generates a 4-panel comprehensive visualization figure:
- Subplot 1: I-ISS 所有入料及出料氚流量 (TEP/NBI Inflows & SDS/WDS Outflows)
- Subplot 2: O-ISS 所有入料及出料氚流量 (TES/WDS/CPS Inflows & SDS/CD1 Outflows)
- Subplot 3: I-ISS 与 O-ISS 动态储氚滞留量 (Tritium Holdup in I-ISS & O-ISS)
- Subplot 4: SDS 储氚系统总滞留量 / 库存 (SDS Tritium Storage Inventory)
"""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def generate_plots():
    base_dir = Path(__file__).parent
    res_file = base_dir / "simulation_results_cycle_res.csv"

    if not res_file.exists():
        alt_file = base_dir / "simulation_results_cycle.csv"
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
    if "i_iss.from_TEP_FCU[1]" in df.columns:
        ax1.plot(df["time"], df["i_iss.from_TEP_FCU[1]"], label="进料: TEP_FCU -> I-ISS (托卡马克排气)", color="#1f77b4", linewidth=2.2)
    if "i_iss.from_NBI[1]" in df.columns:
        ax1.plot(df["time"], df["i_iss.from_NBI[1]"], label="进料: NBI -> I-ISS (中性束注入流)", color="#17becf", linestyle=":", linewidth=2.0)
    if "i_iss.to_SDS[1]" in df.columns:
        ax1.plot(df["time"], df["i_iss.to_SDS[1]"], label="出料: I-ISS -> SDS (高纯 T2+D2 核燃料产物)", color="#ff7f0e", linewidth=2.2)
    if "i_iss.to_WDS[1]" in df.columns:
        ax1.plot(df["time"], df["i_iss.to_WDS[1]"], label="出料: I-ISS -> WDS (CD4 塔顶含氢脱除废气)", color="#2ca02c", linestyle="--", linewidth=2.0)

    ax1.set_title("1. I-ISS 所有进料与出料氚流量动态响应 (I-ISS Tritium Inflows & Outflows)", fontsize=12, fontweight="bold", pad=6)
    ax1.set_ylabel("氚流率 (g/h) [symlog]", fontsize=10)
    ax1.set_yscale("symlog", linthresh=1e-4)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="center right", fontsize=9, framealpha=0.9)

    # =========================================================================
    # Subplot 2: O-ISS 所有入料及出料氚流量
    # =========================================================================
    if "o_iss.from_TES[1]" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_TES[1]"], label="进料: TES -> O-ISS (增殖包层提取氚流)", color="#1f77b4", linewidth=2.2)
    elif "tes.to_O_ISS[1]" in df.columns:
        ax2.plot(df["time"], df["tes.to_O_ISS[1]"], label="进料: TES -> O-ISS (增殖包层提取氚流)", color="#1f77b4", linewidth=2.2)

    if "o_iss.from_WDS[1]" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_WDS[1]"], label="进料: WDS -> O-ISS (水除氚浓缩回收流)", color="#2ca02c", linestyle="--", linewidth=2.0)
    elif "wds.to_O_ISS[1]" in df.columns:
        ax2.plot(df["time"], df["wds.to_O_ISS[1]"], label="进料: WDS -> O-ISS (水除氚浓缩回收流)", color="#2ca02c", linestyle="--", linewidth=2.0)

    if "o_iss.from_CPS[1]" in df.columns:
        ax2.plot(df["time"], df["o_iss.from_CPS[1]"], label="进料: CPS -> O-ISS (冷却剂净化流)", color="#bcbd22", linestyle=":", linewidth=2.0)

    if "o_iss.to_SDS[1]" in df.columns:
        ax2.plot(df["time"], df["o_iss.to_SDS[1]"], label="出料: O-ISS -> SDS (高纯 T2 提纯产物)", color="#ff7f0e", linewidth=2.2)

    if "o_iss.top_CD1[1]" in df.columns:
        ax2.plot(df["time"], df["o_iss.top_CD1[1]"], label="出料: O-ISS CD1 塔顶排空 (洁净富氢尾气)", color="#9467bd", linestyle="-.", linewidth=2.0)

    ax2.set_title("2. O-ISS 所有进料与出料氚流量动态响应 (O-ISS Tritium Inflows & Outflows)", fontsize=12, fontweight="bold", pad=6)
    ax2.set_ylabel("氚流率 (g/h) [symlog]", fontsize=10)
    ax2.set_yscale("symlog", linthresh=1e-4)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="center right", fontsize=9, framealpha=0.9)

    # =========================================================================
    # Subplot 3: I-ISS 与 O-ISS 动态储氚滞留量 (Tritium Holdup)
    # =========================================================================
    has_i_inv = "i_iss.inventory_T" in df.columns
    has_o_inv = "o_iss.inventory_T" in df.columns

    if has_i_inv:
        ax3.plot(df["time"], df["i_iss.inventory_T"], label="I-ISS 内部动态总储氚滞留量 (4塔+2平衡器)", color="#e377c2", linewidth=2.2)
    if has_o_inv:
        ax3.plot(df["time"], df["o_iss.inventory_T"], label="O-ISS 内部动态总储氚滞留量 (3塔+1平衡器)", color="#17becf", linewidth=2.2)
    if has_i_inv and has_o_inv:
        tot_iss = df["i_iss.inventory_T"] + df["o_iss.inventory_T"]
        ax3.plot(df["time"], tot_iss, label="全厂 ISS 总动态储氚滞留量 (I-ISS + O-ISS)", color="#8c564b", linestyle="--", linewidth=2.0)

    ax3.set_title("3. I-ISS 与 O-ISS 内部动态储氚滞留量 (Tritium Holdup in I-ISS & O-ISS)", fontsize=12, fontweight="bold", pad=6)
    ax3.set_ylabel("氚滞留量 (g)", fontsize=10)
    ax3.grid(True, linestyle=":", alpha=0.6)
    ax3.legend(loc="center right", fontsize=9, framealpha=0.9)

    # =========================================================================
    # Subplot 4: SDS 储氚系统总滞留量 (SDS Tritium Inventory)
    # =========================================================================
    if "sds.I[1]" in df.columns:
        ax4.plot(df["time"], df["sds.I[1]"], label="SDS 储氚库存 (SDS Tritium Storage Inventory)", color="#d62728", linewidth=2.4)

    ax4.set_title("4. 全厂 SDS 储氚库存动态累积 (SDS Tritium Storage Inventory)", fontsize=12, fontweight="bold", pad=6)
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
    print("           全厂燃料闭环 0-D 高保真动态仿真稳态数据表")
    print("=" * 76)
    print("【I-ISS 内燃料循环】:")
    if "i_iss.from_TEP_FCU[1]" in df.columns:
        print(f"  - 进料 TEP_FCU 平均氚流量:       {ss['i_iss.from_TEP_FCU[1]'].mean():.4f} g/h")
    if "i_iss.to_SDS[1]" in df.columns:
        print(f"  - 出料 to SDS 产氚流率:          {ss['i_iss.to_SDS[1]'].mean():.4f} g/h")
    if "i_iss.to_WDS[1]" in df.columns:
        print(f"  - 出料 to WDS 废气氚流量:        {ss['i_iss.to_WDS[1]'].mean():.4e} g/h")
    if has_i_inv:
        print(f"  - I-ISS 稳态储氚滞留量 (Holdup): {ss['i_iss.inventory_T'].mean():.4f} g")

    print("\n【O-ISS 外燃料循环】:")
    if "o_iss.from_TES[1]" in df.columns:
        print(f"  - 进料 TES 平均氚流量:           {ss['o_iss.from_TES[1]'].mean():.4f} g/h")
    if "o_iss.from_WDS[1]" in df.columns:
        print(f"  - 进料 WDS 平均氚流量:           {ss['o_iss.from_WDS[1]'].mean():.4f} g/h")
    if "o_iss.to_SDS[1]" in df.columns:
        print(f"  - 出料 to SDS 产氚流率:          {ss['o_iss.to_SDS[1]'].mean():.4f} g/h")
    if "o_iss.top_CD1[1]" in df.columns:
        print(f"  - 出料 CD1 顶废气排空氚流量:     {ss['o_iss.top_CD1[1]'].mean():.4e} g/h")
    if has_o_inv:
        print(f"  - O-ISS 稳态储氚滞留量 (Holdup): {ss['o_iss.inventory_T'].mean():.4f} g")

    if has_i_inv and has_o_inv:
        tot_iss_t = ss['i_iss.inventory_T'].mean() + ss['o_iss.inventory_T'].mean()
        print(f"\n【全厂 ISS (I+O) 总储氚滞留量】:    {tot_iss_t:.4f} g")

    if "sds.I[1]" in df.columns:
        print(f"\n【全厂 SDS 储氚总盘存】 (5000h 末): {df['sds.I[1]'].iloc[-1]:.2f} g")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    generate_plots()
