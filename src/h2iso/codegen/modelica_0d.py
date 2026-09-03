"""Modelica 0-D surrogate model and parameter injection generator.

Generates Generic_ISS Modelica package (6-component molecular basis) and
extracts parameter override files from h2iso flowsheet/benchmark results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from h2iso.species import SPECIES, SPECIES_ORDER


def generate_generic_iss_mo() -> str:
    """Generate the pure Generic_ISS Modelica library code (Core physical models).

    Strictly corresponds to Wang 2022 CFETR ISS-I and ISS-O multi-column benchmarks
    on 6-species molecular basis [H2, HD, HT, D2, DT, T2].

    Includes:
    - Column_0D_6: 6-species molecular surrogate distillation column with tritium holdup
    - Equilibrator_0D_6: 6-species catalytic isotopic equilibrator with reaction chemistry
    - ISS_I_Core: 4-column + 2-equilibrator cascade (Wang 2022 ISS-I) with total tritium inventory
    - ISS_O_Core: 3-column + 1-equilibrator cascade (Wang 2022 ISS-O) with total tritium inventory

    Returns
    -------
    str
        Pure Generic_ISS Modelica package source code.
    """
    mw_h2 = SPECIES["H2"].molar_mass
    mw_hd = SPECIES["HD"].molar_mass
    mw_ht = SPECIES["HT"].molar_mass
    mw_d2 = SPECIES["D2"].molar_mass
    mw_dt = SPECIES["DT"].molar_mass
    mw_t2 = SPECIES["T2"].molar_mass
    mw_t_atom = 3.016049

    return f'''\
package Generic_ISS
  "Generic Hydrogen Isotope Separation System (ISS) High-Fidelity Physics Core Library"

  // ========================================================================
  // 1. 基础物理降阶单元 (Base Units - 6-Species Molecular Basis)
  // 组分索引映射: 1:H2, 2:HD, 3:HT, 4:D2, 5:DT, 6:T2
  // ========================================================================

  model Column_0D_6 "6-组分高保真精馏塔 0-D 动态代理单元"
    // 端口定义 (6 维分子质量流量 g/h)
    Modelica.Blocks.Interfaces.RealInput feed[6] "进料质量流率 (g/h)"
      annotation(Placement(transformation(extent={{{{-120,-10}},{{-100,10}}}})));
    Modelica.Blocks.Interfaces.RealOutput top[6] "塔顶产品质量流率 (g/h)"
      annotation(Placement(transformation(extent={{{{100,30}},{{120,50}}}})));
    Modelica.Blocks.Interfaces.RealOutput bottom[6] "塔釜产品质量流率 (g/h)"
      annotation(Placement(transformation(extent={{{{100,-50}},{{120,-30}}}})));

    // 状态输出端口
    Modelica.Blocks.Interfaces.RealOutput inventory_T "塔内总储氚滞留量 (g)"
      annotation(Placement(transformation(extent={{{{100,-10}},{{120,10}}}})));

    // --- 动态注入参数 (由 h2iso 求解结果自动覆盖) ---
    parameter Real m_top_ref[6] = {{0,0,0,0,0,0}} "h2iso 塔顶 6 组分参考质量流量 (g/h)" annotation(Evaluate=false);
    parameter Real m_bottom_ref[6] = {{0,0,0,0,0,0}} "h2iso 塔底 6 组分参考质量流量 (g/h)" annotation(Evaluate=false);
    parameter Real tau = 1.0 "塔特征停留时间 (h) = M_total / m_feed" annotation(Evaluate=false);
    parameter Real N_stages = 0 "理论板数" annotation(Evaluate=false);
    parameter Real R = 0 "回流比" annotation(Evaluate=false);
    parameter Real T_top = 0 "塔顶温度 (K)" annotation(Evaluate=false);
    parameter Real T_bottom = 0 "塔釜温度 (K)" annotation(Evaluate=false);

    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    // --- 内部状态与代数变量 ---
    Real I[6](start={{0,0,0,0,0,0}}) "塔内 6 组分动态持液滞留量 (g)";
    Real outflow[6] "总流出流率 (g/h)";
    Real SF_top[6] "各组分塔顶分离系数 (无量纲)";

  equation
    for i in 1:6 loop
      // 1. 动态质量守恒：流入 - 流出 = 滞留量导数
      der(I[i]) = feed[i] - outflow[i];

      // 2. 一阶水力学滞后
      outflow[i] = I[i] / max(tau, 1e-4);

      // 3. 基于 h2iso 稳态高保真分离比 (带除零极小值保护)
      SF_top[i] = if (m_top_ref[i] + m_bottom_ref[i] > 1e-12)
                  then m_top_ref[i] / (m_top_ref[i] + m_bottom_ref[i])
                  else 0.0;

      // 4. 产物动态分流
      top[i] = SF_top[i] * outflow[i];
      bottom[i] = (1.0 - SF_top[i]) * outflow[i];
    end for;

    // 5. 塔内原子氚总滞留量 (g)
    inventory_T = I[3]*(MW_T/MW[3]) + I[5]*(MW_T/MW[5]) + I[6];
  end Column_0D_6;


  model Equilibrator_0D_6 "6-组分催化同位素交换平衡反应器"
    // 分子摩尔质量 (g/mol): [H2, HD, HT, D2, DT, T2]
    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};
    parameter Real tau = 0.1 "平衡器停留时间常数 (h)" annotation(Evaluate=false);

    Modelica.Blocks.Interfaces.RealInput feed[6] "进料 (g/h)"
      annotation(Placement(transformation(extent={{{{-120,-10}},{{-100,10}}}})));
    Modelica.Blocks.Interfaces.RealOutput outflow[6] "平衡产物 (g/h)"
      annotation(Placement(transformation(extent={{{{100,-10}},{{120,10}}}})));
    Modelica.Blocks.Interfaces.RealOutput inventory_T "平衡器内总储氚滞留量 (g)";

    Real I[6](start={{0,0,0,0,0,0}}) "平衡器内滞留量 (g)";
    Real flow_hold[6] "滞留流出流率 (g/h)";
    Real n_in[6] "各分子摩尔流率 (mol/h)";
    Real n_H, n_D, n_T, n_atom_tot "原子摩尔流率与总原子数 (mol/h)";
    Real a_H, a_D, a_T "进料原子分数";
    Real x_eq[6] "化学平衡分子摩尔分数";
    Real n_out_tot "输出总分子摩尔流率 (mol/h)";

  equation
    // 1. 动态持液滞留
    for i in 1:6 loop
      der(I[i]) = feed[i] - flow_hold[i];
      flow_hold[i] = I[i] / max(tau, 1e-4);
      n_in[i] = flow_hold[i] / MW[i];
    end for;

    // 2. 严格原子守恒与原子分数提取
    n_H = 2.0 * n_in[1] + n_in[2] + n_in[3];
    n_D = n_in[2] + 2.0 * n_in[4] + n_in[5];
    n_T = n_in[3] + n_in[5] + 2.0 * n_in[6];
    n_atom_tot = n_H + n_D + n_T;

    a_H = if n_atom_tot > 1e-12 then n_H / n_atom_tot else 0.0;
    a_D = if n_atom_tot > 1e-12 then n_D / n_atom_tot else 0.0;
    a_T = if n_atom_tot > 1e-12 then n_T / n_atom_tot else 0.0;

    // 3. 统计热力学同位素重组平衡分配 (高温统计极限 K_eq=4 近似，满足整体同位素原子守恒)
    x_eq[1] = a_H * a_H;         // H2
    x_eq[2] = 2.0 * a_H * a_D;   // HD
    x_eq[3] = 2.0 * a_H * a_T;   // HT
    x_eq[4] = a_D * a_D;         // D2
    x_eq[5] = 2.0 * a_D * a_T;   // DT
    x_eq[6] = a_T * a_T;         // T2

    // 4. 重构 6 维分子输出质量流量
    n_out_tot = 0.5 * n_atom_tot;
    for i in 1:6 loop
      outflow[i] = n_out_tot * x_eq[i] * MW[i];
    end for;

    // 5. 储氚滞留量
    inventory_T = I[3]*(MW_T/MW[3]) + I[5]*(MW_T/MW[5]) + I[6];
  end Equilibrator_0D_6;


  // ========================================================================
  // 2. 核心拓扑 (Core Topologies - 严格匹配 Wang 2022)
  // ========================================================================

  model ISS_I_Core "ISS-I 内燃料循环物理核心 (4塔 + 2平衡器)"
    parameter Integer N = 6 "分子组分维度";
    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    // 纯物理边界端口 (6 维分子质量流 g/h)
    Modelica.Blocks.Interfaces.RealInput feed_TEP[N] "TEP 进料 (进 CD1)";
    Modelica.Blocks.Interfaces.RealInput feed_NBI[N] "NBI 进料 (进 CD2)";

    Modelica.Blocks.Interfaces.RealOutput prod_T2_SDS[N] "高纯 T2 核燃料产物 -> SDS (CD3 塔底)";
    Modelica.Blocks.Interfaces.RealOutput prod_D2_SDS[N] "高纯 D2 产物 -> SDS (CD2 顶 + CD4 底)";
    Modelica.Blocks.Interfaces.RealOutput waste_HD_WDS[N] "含氢废气 -> WDS 排气 (CD4 顶)";
    Modelica.Blocks.Interfaces.RealOutput total_inventory[N] "全系统 6 维分子总动态持液量 (g)";
    Modelica.Blocks.Interfaces.RealOutput inventory_T "ISS-I 动态总储氚滞留量 (g)"
      annotation(Placement(transformation(extent={{{{100,0}},{{120,20}}}})));

    // 实例化物理单元
    Column_0D_6 CD1, CD2, CD3, CD4;
    Equilibrator_0D_6 E1, E2;

  equation
    // 1. CD1: 接收 TEP 进料与 E1 (CD3 顶流催化平衡后) 的回流
    CD1.feed = feed_TEP + E1.outflow;

    // 2. CD2: 接收 NBI 进料
    CD2.feed = feed_NBI;

    // 3. CD3: 接收 CD1 塔釜与 CD2 塔釜重组分
    CD3.feed = CD1.bottom + CD2.bottom;

    // 4. E1 & E2 催化平衡器
    E1.feed = CD3.top; // DT 转化为 D2 + T2 回流至 CD1
    E2.feed = CD1.top; // 杂质流催化重组送 CD4

    // 5. CD4: 接收 E2 出口物料进行脱氢
    CD4.feed = E2.outflow;

    // 6. 系统输出边界汇聚
    prod_T2_SDS = CD3.bottom;
    prod_D2_SDS = CD2.top + CD4.bottom;
    waste_HD_WDS = CD4.top;

    // 7. 提取全系统各分子滞留量总和
    for i in 1:N loop
      total_inventory[i] = CD1.I[i] + CD2.I[i] + CD3.I[i] + CD4.I[i] + E1.I[i] + E2.I[i];
    end for;

    // 8. 全系统原子氚总滞留量 (g)
    inventory_T = total_inventory[3]*(MW_T/MW[3]) + total_inventory[5]*(MW_T/MW[5]) + total_inventory[6];
  end ISS_I_Core;


  model ISS_O_Core "ISS-O 外燃料循环物理核心 (3塔 + 1平衡器)"
    parameter Integer N = 6 "分子组分维度";
    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    // 纯物理边界端口 (6 维分子质量流 g/h)
    Modelica.Blocks.Interfaces.RealInput feed_WDS[N] "WDS 进料 (进 CD1)";
    Modelica.Blocks.Interfaces.RealInput feed_TES[N] "TES 进料 (进 CD2)";

    Modelica.Blocks.Interfaces.RealOutput prod_T2_SDS[N] "高纯 T2 浓缩产物 -> SDS (CD3 塔底)";
    Modelica.Blocks.Interfaces.RealOutput waste_HD[N] "洁净废气排空 (CD1 塔顶)";
    Modelica.Blocks.Interfaces.RealOutput total_inventory[N] "全系统 6 维分子总动态持液量 (g)";
    Modelica.Blocks.Interfaces.RealOutput inventory_T "ISS-O 动态总储氚滞留量 (g)"
      annotation(Placement(transformation(extent={{{{100,0}},{{120,20}}}})));

    // 实例化物理单元
    Column_0D_6 CD1, CD2, CD3;
    Equilibrator_0D_6 E;

  equation
    // 1. CD1: 接收 WDS 进料与 CD2 塔顶富氢回流
    CD1.feed = feed_WDS + CD2.top;

    // 2. CD2: 接收 TES 进料、CD1 塔釜富同位素流及 CD3 塔顶回流
    CD2.feed = feed_TES + CD1.bottom + CD3.top;

    // 3. E 催化平衡器: 接收 CD2 塔釜纯 HT 进行重组 (2HT -> H2 + T2)
    E.feed = CD2.bottom;

    // 4. CD3: 接收平衡转化后产物进行最终 T2 提纯
    CD3.feed = E.outflow;

    // 5. 系统输出边界汇聚
    waste_HD = CD1.top;
    prod_T2_SDS = CD3.bottom;

    // 6. 提取全系统各分子滞留量总和
    for i in 1:N loop
      total_inventory[i] = CD1.I[i] + CD2.I[i] + CD3.I[i] + E.I[i];
    end for;

    // 7. 全系统原子氚总滞留量 (g)
    inventory_T = total_inventory[3]*(MW_T/MW[3]) + total_inventory[5]*(MW_T/MW[5]) + total_inventory[6];
  end ISS_O_Core;

end Generic_ISS;
'''


def generate_iss_adapters_mo(adapter_mode: str = "all") -> str:
    """Generate the Generic_ISS_Adapters Modelica library code.

    Parameters
    ----------
    adapter_mode : str
        'all': Include both 5D vector and 3LC scalar adapters.
        '5d': Include only 5D vector multi-component adapters (example_model.mo).
        '3lc': Include only 3LC scalar adapters (CFEDR_2870_3lc_ssp.mo).

    Returns
    -------
    str
        Generic_ISS_Adapters Modelica package source code.
    """
    mw_h2 = SPECIES["H2"].molar_mass
    mw_hd = SPECIES["HD"].molar_mass
    mw_ht = SPECIES["HT"].molar_mass
    mw_d2 = SPECIES["D2"].molar_mass
    mw_dt = SPECIES["DT"].molar_mass
    mw_t2 = SPECIES["T2"].molar_mass

    mw_t_atom = 3.016049
    mw_d_atom = 2.014102
    mw_h_atom = 1.007825

    code_5d = f'''\
  // ========================================================================
  // 1. 多组分 5D/6D 适配器外壳 (Multi-Component 5D/6D Adapter Shells)
  // 将 5 维原子质量流 [T, D, H, He, Imp] (g/h) 映射为 6 维分子流 [H2..T2]
  // 工程假设：He (组分4) 与 Imp (组分5) 假设在前级净化系统已脱除，ISS 内部仅追踪同位素，出口恒置0
  // ========================================================================

  model ISS_I_Adapter "ISS-I 多组分 5D/6D 双向适配器 (兼容 example_model.I_ISS 接口)"
    // 5 维外部接口
    Modelica.Blocks.Interfaces.RealInput from_TEP_FCU[5] "来自 TEP_FCU 进料 [T,D,H,He,Imp] (g/h)"
      annotation(Placement(transformation(extent={{{{-120,30}},{{-100,50}}}})));
    Modelica.Blocks.Interfaces.RealInput from_NBI[5] "来自 NBI 进料 [T,D,H,He,Imp] (g/h)"
      annotation(Placement(transformation(extent={{{{-120,-50}},{{-100,-30}}}})));

    Modelica.Blocks.Interfaces.RealOutput to_SDS[5] "输出到 SDS 系统 (高纯燃料产物) (g/h)"
      annotation(Placement(transformation(extent={{{{100,30}},{{120,50}}}})));
    Modelica.Blocks.Interfaces.RealOutput to_WDS[5] "输出到 WDS 系统 (CD4 塔顶含氢废气) (g/h)"
      annotation(Placement(transformation(extent={{{{100,-50}},{{120,-30}}}})));

    // 细分产物别名端口
    Modelica.Blocks.Interfaces.RealOutput to_SDS_T2[5] "高纯 T2 产物 -> SDS (g/h)";
    Modelica.Blocks.Interfaces.RealOutput to_SDS_D2[5] "高纯 D2 产物 -> SDS (g/h)";
    Modelica.Blocks.Interfaces.RealOutput to_WDS_waste[5] "含氢废气 -> WDS (g/h)";
    Modelica.Blocks.Interfaces.RealOutput total_inventory_5D[5] "全系统 5 组分总盘存 (g)";
    Modelica.Blocks.Interfaces.RealOutput inventory_T "ISS-I 动态总储氚滞留量 (g)"
      annotation(Placement(transformation(extent={{{{100,-10}},{{120,10}}}})));

    // 实例化 6 维物理核心
    Generic_ISS.ISS_I_Core core;

    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW_D = {mw_d_atom:.6f};
    final parameter Real MW_H = {mw_h_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    Real n_tep_T, n_tep_D, n_tep_H, n_tep_tot;
    Real a_tep_T, a_tep_D, a_tep_H;
    Real n_nbi_T, n_nbi_D, n_nbi_H, n_nbi_tot;
    Real a_nbi_T, a_nbi_D, a_nbi_H;

  equation
    // 1. TEP 进料适配 (5D -> 6D 统计平衡分配)
    n_tep_T = from_TEP_FCU[1] / MW_T;
    n_tep_D = from_TEP_FCU[2] / MW_D;
    n_tep_H = from_TEP_FCU[3] / MW_H;
    n_tep_tot = n_tep_T + n_tep_D + n_tep_H;
    a_tep_T = if n_tep_tot > 1e-12 then n_tep_T / n_tep_tot else 0.0;
    a_tep_D = if n_tep_tot > 1e-12 then n_tep_D / n_tep_tot else 0.0;
    a_tep_H = if n_tep_tot > 1e-12 then n_tep_H / n_tep_tot else 0.0;

    core.feed_TEP[1] = 0.5 * n_tep_tot * (a_tep_H * a_tep_H) * MW[1];
    core.feed_TEP[2] = 0.5 * n_tep_tot * (2.0 * a_tep_H * a_tep_D) * MW[2];
    core.feed_TEP[3] = 0.5 * n_tep_tot * (2.0 * a_tep_H * a_tep_T) * MW[3];
    core.feed_TEP[4] = 0.5 * n_tep_tot * (a_tep_D * a_tep_D) * MW[4];
    core.feed_TEP[5] = 0.5 * n_tep_tot * (2.0 * a_tep_D * a_tep_T) * MW[5];
    core.feed_TEP[6] = 0.5 * n_tep_tot * (a_tep_T * a_tep_T) * MW[6];

    // 2. NBI 进料适配 (5D -> 6D)
    n_nbi_T = from_NBI[1] / MW_T;
    n_nbi_D = from_NBI[2] / MW_D;
    n_nbi_H = from_NBI[3] / MW_H;
    n_nbi_tot = n_nbi_T + n_nbi_D + n_nbi_H;
    a_nbi_T = if n_nbi_tot > 1e-12 then n_nbi_T / n_nbi_tot else 0.0;
    a_nbi_D = if n_nbi_tot > 1e-12 then n_nbi_D / n_nbi_tot else 0.0;
    a_nbi_H = if n_nbi_tot > 1e-12 then n_nbi_H / n_nbi_tot else 0.0;

    core.feed_NBI[1] = 0.5 * n_nbi_tot * (a_nbi_H * a_nbi_H) * MW[1];
    core.feed_NBI[2] = 0.5 * n_nbi_tot * (2.0 * a_nbi_H * a_nbi_D) * MW[2];
    core.feed_NBI[3] = 0.5 * n_nbi_tot * (2.0 * a_nbi_H * a_nbi_T) * MW[3];
    core.feed_NBI[4] = 0.5 * n_nbi_tot * (a_nbi_D * a_nbi_D) * MW[4];
    core.feed_NBI[5] = 0.5 * n_nbi_tot * (2.0 * a_nbi_D * a_nbi_T) * MW[5];
    core.feed_NBI[6] = 0.5 * n_nbi_tot * (a_nbi_T * a_nbi_T) * MW[6];

    // 3. 出料适配 (6D -> 5D 精确原子质量加权折算)
    to_SDS_T2[1] = core.prod_T2_SDS[3]*(MW_T/MW[3]) + core.prod_T2_SDS[5]*(MW_T/MW[5]) + core.prod_T2_SDS[6];
    to_SDS_T2[2] = core.prod_T2_SDS[2]*(MW_D/MW[2]) + core.prod_T2_SDS[4] + core.prod_T2_SDS[5]*(MW_D/MW[5]);
    to_SDS_T2[3] = core.prod_T2_SDS[1] + core.prod_T2_SDS[2]*(MW_H/MW[2]) + core.prod_T2_SDS[3]*(MW_H/MW[3]);
    to_SDS_T2[4] = 0.0;
    to_SDS_T2[5] = 0.0;

    to_SDS_D2[1] = core.prod_D2_SDS[3]*(MW_T/MW[3]) + core.prod_D2_SDS[5]*(MW_T/MW[5]) + core.prod_D2_SDS[6];
    to_SDS_D2[2] = core.prod_D2_SDS[2]*(MW_D/MW[2]) + core.prod_D2_SDS[4] + core.prod_D2_SDS[5]*(MW_D/MW[5]);
    to_SDS_D2[3] = core.prod_D2_SDS[1] + core.prod_D2_SDS[2]*(MW_H/MW[2]) + core.prod_D2_SDS[3]*(MW_H/MW[3]);
    to_SDS_D2[4] = 0.0;
    to_SDS_D2[5] = 0.0;

    to_WDS_waste[1] = core.waste_HD_WDS[3]*(MW_T/MW[3]) + core.waste_HD_WDS[5]*(MW_T/MW[5]) + core.waste_HD_WDS[6];
    to_WDS_waste[2] = core.waste_HD_WDS[2]*(MW_D/MW[2]) + core.waste_HD_WDS[4] + core.waste_HD_WDS[5]*(MW_D/MW[5]);
    to_WDS_waste[3] = core.waste_HD_WDS[1] + core.waste_HD_WDS[2]*(MW_H/MW[2]) + core.waste_HD_WDS[3]*(MW_H/MW[3]);
    to_WDS_waste[4] = 0.0;
    to_WDS_waste[5] = 0.0;

    // 对接标准回路端口: to_SDS (T2 + D2 产品总和), to_WDS (含氢排气)
    to_SDS = to_SDS_T2 + to_SDS_D2;
    to_WDS = to_WDS_waste;

    // 4. 盘存映射 (6D -> 5D)
    total_inventory_5D[1] = core.total_inventory[3]*(MW_T/MW[3]) + core.total_inventory[5]*(MW_T/MW[5]) + core.total_inventory[6];
    total_inventory_5D[2] = core.total_inventory[2]*(MW_D/MW[2]) + core.total_inventory[4] + core.total_inventory[5]*(MW_D/MW[5]);
    total_inventory_5D[3] = core.total_inventory[1] + core.total_inventory[2]*(MW_H/MW[2]) + core.total_inventory[3]*(MW_H/MW[3]);
    total_inventory_5D[4] = 0.0;
    total_inventory_5D[5] = 0.0;

    // 5. 动态总储氚滞留量
    inventory_T = total_inventory_5D[1];
  end ISS_I_Adapter;


  model ISS_O_Adapter "ISS-O 多组分 5D/6D 双向适配器 (兼容 example_model.O_ISS 接口)"
    // 5 维外部接口 (严格对应 example_model.O_ISS 端口命名)
    Modelica.Blocks.Interfaces.RealInput from_CPS[5] "来自 CPS 的输入 (g/h)"
      annotation(Placement(transformation(extent={{{{-120,40}},{{-100,60}}}})));
    Modelica.Blocks.Interfaces.RealInput from_WDS[5] "来自 WDS 的输入 (g/h)"
      annotation(Placement(transformation(extent={{{{-120,0}},{{-100,20}}}})));
    Modelica.Blocks.Interfaces.RealInput from_TES[5] "来自 TES 的输入 (g/h)"
      annotation(Placement(transformation(extent={{{{-120,-40}},{{-100,-20}}}})));

    Modelica.Blocks.Interfaces.RealOutput to_SDS[5] "输出到 SDS 系统 (高纯 T2 产物) (g/h)"
      annotation(Placement(transformation(extent={{{{100,-30}},{{120,-10}}}})));
    Modelica.Blocks.Interfaces.RealOutput top_CD1[5] "CD1 塔顶洁净废气排放 (g/h)"
      annotation(Placement(transformation(extent={{{{100,30}},{{120,50}}}})));
    Modelica.Blocks.Interfaces.RealOutput waste_HD[5] "洁净废气排空 (别名端口) (g/h)";
    Modelica.Blocks.Interfaces.RealOutput total_inventory_5D[5] "全系统 5 组分总盘存 (g)";
    Modelica.Blocks.Interfaces.RealOutput inventory_T "ISS-O 动态总储氚滞留量 (g)"
      annotation(Placement(transformation(extent={{{{100,-10}},{{120,10}}}})));

    // 实例化 6 维物理核心
    Generic_ISS.ISS_O_Core core;

    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW_D = {mw_d_atom:.6f};
    final parameter Real MW_H = {mw_h_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    Real n_wds_T, n_wds_D, n_wds_H, n_wds_tot;
    Real a_wds_T, a_wds_D, a_wds_H;
    Real n_tes_T, n_tes_D, n_tes_H, n_tes_tot;
    Real a_tes_T, a_tes_D, a_tes_H;

  equation
    // 1. WDS 进料适配
    n_wds_T = from_WDS[1] / MW_T;
    n_wds_D = from_WDS[2] / MW_D;
    n_wds_H = from_WDS[3] / MW_H;
    n_wds_tot = n_wds_T + n_wds_D + n_wds_H;
    a_wds_T = if n_wds_tot > 1e-12 then n_wds_T / n_wds_tot else 0.0;
    a_wds_D = if n_wds_tot > 1e-12 then n_wds_D / n_wds_tot else 0.0;
    a_wds_H = if n_wds_tot > 1e-12 then n_wds_H / n_wds_tot else 0.0;

    core.feed_WDS[1] = 0.5 * n_wds_tot * (a_wds_H * a_wds_H) * MW[1];
    core.feed_WDS[2] = 0.5 * n_wds_tot * (2.0 * a_wds_H * a_wds_D) * MW[2];
    core.feed_WDS[3] = 0.5 * n_wds_tot * (2.0 * a_wds_H * a_wds_T) * MW[3];
    core.feed_WDS[4] = 0.5 * n_wds_tot * (a_wds_D * a_wds_D) * MW[4];
    core.feed_WDS[5] = 0.5 * n_wds_tot * (2.0 * a_wds_D * a_wds_T) * MW[5];
    core.feed_WDS[6] = 0.5 * n_wds_tot * (a_wds_T * a_wds_T) * MW[6];

    // 2. TES + CPS 进料适配 (CPS 汇入 TES 输入流)
    n_tes_T = (from_TES[1] + from_CPS[1]) / MW_T;
    n_tes_D = (from_TES[2] + from_CPS[2]) / MW_D;
    n_tes_H = (from_TES[3] + from_CPS[3]) / MW_H;
    n_tes_tot = n_tes_T + n_tes_D + n_tes_H;
    a_tes_T = if n_tes_tot > 1e-12 then n_tes_T / n_tes_tot else 0.0;
    a_tes_D = if n_tes_tot > 1e-12 then n_tes_D / n_tes_tot else 0.0;
    a_tes_H = if n_tes_tot > 1e-12 then n_tes_H / n_tes_tot else 0.0;

    core.feed_TES[1] = 0.5 * n_tes_tot * (a_tes_H * a_tes_H) * MW[1];
    core.feed_TES[2] = 0.5 * n_tes_tot * (2.0 * a_tes_H * a_tes_D) * MW[2];
    core.feed_TES[3] = 0.5 * n_tes_tot * (2.0 * a_tes_H * a_tes_T) * MW[3];
    core.feed_TES[4] = 0.5 * n_tes_tot * (a_tes_D * a_tes_D) * MW[4];
    core.feed_TES[5] = 0.5 * n_tes_tot * (2.0 * a_tes_D * a_tes_T) * MW[5];
    core.feed_TES[6] = 0.5 * n_tes_tot * (a_tes_T * a_tes_T) * MW[6];

    // 3. 出料适配
    to_SDS[1] = core.prod_T2_SDS[3]*(MW_T/MW[3]) + core.prod_T2_SDS[5]*(MW_T/MW[5]) + core.prod_T2_SDS[6];
    to_SDS[2] = core.prod_T2_SDS[2]*(MW_D/MW[2]) + core.prod_T2_SDS[4] + core.prod_T2_SDS[5]*(MW_D/MW[5]);
    to_SDS[3] = core.prod_T2_SDS[1] + core.prod_T2_SDS[2]*(MW_H/MW[2]) + core.prod_T2_SDS[3]*(MW_H/MW[3]);
    to_SDS[4] = 0.0;
    to_SDS[5] = 0.0;

    top_CD1[1] = core.waste_HD[3]*(MW_T/MW[3]) + core.waste_HD[5]*(MW_T/MW[5]) + core.waste_HD[6];
    top_CD1[2] = core.waste_HD[2]*(MW_D/MW[2]) + core.waste_HD[4] + core.waste_HD[5]*(MW_D/MW[5]);
    top_CD1[3] = core.waste_HD[1] + core.waste_HD[2]*(MW_H/MW[2]) + core.waste_HD[3]*(MW_H/MW[3]);
    top_CD1[4] = 0.0;
    top_CD1[5] = 0.0;

    waste_HD = top_CD1;

    // 4. 盘存映射
    total_inventory_5D[1] = core.total_inventory[3]*(MW_T/MW[3]) + core.total_inventory[5]*(MW_T/MW[5]) + core.total_inventory[6];
    total_inventory_5D[2] = core.total_inventory[2]*(MW_D/MW[2]) + core.total_inventory[4] + core.total_inventory[5]*(MW_D/MW[5]);
    total_inventory_5D[3] = core.total_inventory[1] + core.total_inventory[2]*(MW_H/MW[2]) + core.total_inventory[3]*(MW_H/MW[3]);
    total_inventory_5D[4] = 0.0;
    total_inventory_5D[5] = 0.0;

    // 5. 动态总储氚滞留量
    inventory_T = total_inventory_5D[1];
  end ISS_O_Adapter;
'''

    code_3lc = f'''\
  // ========================================================================
  // 3-Level Confinement (3LC) 标量氚流适配器 (针对 CFEDR_3LC 系统)
  // 将 1 维标量纯氚质量流量 (g/h) 映射为 6 维分子流 [H2..T2] 并实现三级包容安全审计
  // ========================================================================

  model ISS_I_3LC_Adapter "ISS-I 高保真 0-D 物理核心适配器 (针对 CFEDR_3LC 标量氚流与三级包容系统)"
    // 外部标量氚质量流率端口 (g/h)
    Modelica.Blocks.Interfaces.RealInput from_TEP "来自 TEP 排气净化进料 (g/h 纯氚当量)"
      annotation(Placement(transformation(extent={{{{-120,-10}},{{-100,10}}}})));

    Modelica.Blocks.Interfaces.RealOutput to_SDS "输出至 SDS 储氚系统的高纯燃料 (g/h 纯氚)"
      annotation(Placement(transformation(extent={{{{100,30}},{{120,50}}}})));
    Modelica.Blocks.Interfaces.RealOutput to_WDS "输出至 WDS 的含氢废气微量截留氚 (g/h)"
      annotation(Placement(transformation(extent={{{{100,0}},{{120,20}}}})));
    Modelica.Blocks.Interfaces.RealOutput to_VDS "向 VDS (通风除氚系统) 的微量渗透泄漏 (g/h)"
      annotation(Placement(transformation(extent={{{{100,-30}},{{120,-10}}}})));
    Modelica.Blocks.Interfaces.RealOutput to_Secondary "向二级包容边界 (手套箱/密封室) 的微量泄漏 (g/h)"
      annotation(Placement(transformation(extent={{{{100,-60}},{{120,-40}}}})));

    // 内部宏观状态与核安全审计变量 (与 CFEDR 接口完全对齐)
    Real inventory(unit="g", start = 0) "ISS-I 动态总储氚滞留量 (g)";
    Real inflow(unit="g/h", start = 0) "总进料氚流率 (g/h)";
    Real outflow(unit="g/h", start = 0) "总出料氚流率 (g/h)";
    Real inv_HT(unit="g", start = 0) "HT 分子形态储氚滞留量 (g)";
    Real inv_HTO(unit="g", start = 0) "HTO 分子形态储氚滞留量 (g)";
    Real decay_rate(unit="g/h") "氚放射性衰变损失率 (g/h)";

    // 适配参数 (与 CFEDR 默认兼容)
    parameter Real Epsilon(unit="1") = 1e-4 "微量泄漏率系数";
    parameter Real EtoV(unit="1") = 0.99 "泄漏物分配至 VDS 的比例 (其余进入二级包容)";
    parameter Real Decay(unit="1/h") = 6.42e-6 "氚衰变常数 (1/h)";
    parameter Real T(unit="h") = 6.0 "水力学特征时间常数 (h)";
    parameter Real Threshold(unit="g") = 300 "门限阈值 (兼容 CFEDR)";

    // 实例化 6 组分机理核心
    Generic_ISS.ISS_I_Core core;

    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW_D = {mw_d_atom:.6f};
    final parameter Real MW_H = {mw_h_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    Real n_T, n_tot;

  equation
    // 1. TEP 进料适配 (标量氚流量 -> 6 维分子进料，按等摩尔 D-T 等离子体排气重构)
    n_T = max(0.0, from_TEP) / MW_T;
    n_tot = 2.0 * n_T; // D:T = 1:1

    core.feed_TEP[1] = 0.0;
    core.feed_TEP[2] = 0.0;
    core.feed_TEP[3] = 0.0;
    core.feed_TEP[4] = 0.25 * n_T * MW[4]; // D2 (0.25 n_T moles)
    core.feed_TEP[5] = 0.50 * n_T * MW[5]; // DT (0.50 n_T moles)
    core.feed_TEP[6] = 0.25 * n_T * MW[6]; // T2 (0.25 n_T moles)

    core.feed_NBI = {{0.0, 0.0, 0.0, 0.0, 0.0, 0.0}};

    // 2. 出料适配 (6D -> 1D 纯氚质量流量折算)
    to_SDS = (core.prod_T2_SDS[3]*(MW_T/MW[3]) + core.prod_T2_SDS[5]*(MW_T/MW[5]) + core.prod_T2_SDS[6])
           + (core.prod_D2_SDS[3]*(MW_T/MW[3]) + core.prod_D2_SDS[5]*(MW_T/MW[5]) + core.prod_D2_SDS[6]);
    to_WDS = core.waste_HD_WDS[3]*(MW_T/MW[3]) + core.waste_HD_WDS[5]*(MW_T/MW[5]) + core.waste_HD_WDS[6];

    inflow = from_TEP;
    outflow = to_SDS + to_WDS;

    // 3. 3-Level Confinement 动态泄漏与安全审计
    to_VDS = Epsilon * EtoV * outflow;
    to_Secondary = Epsilon * (1.0 - EtoV) * outflow;

    // 4. 内部动态盘存与物性
    inventory = core.inventory_T;
    inv_HT = core.total_inventory[3]*(MW_T/MW[3]);
    inv_HTO = 0.0;
    decay_rate = inventory * Decay;
  end ISS_I_3LC_Adapter;


  model ISS_O_3LC_Adapter "ISS-O 高保真 0-D 物理核心适配器 (针对 CFEDR_3LC 标量氚流与三级包容系统)"
    // 外部标量氚质量流率端口 (g/h)
    Modelica.Blocks.Interfaces.RealInput from_CPS_PFC "来自 CPS_PFC 进料 (g/h 纯氚当量)"
      annotation(Placement(transformation(extent={{{{-120,40}},{{-100,60}}}})));
    Modelica.Blocks.Interfaces.RealInput from_CPS_BZ "来自 CPS_BZ 进料 (g/h 纯氚当量)"
      annotation(Placement(transformation(extent={{{{-120,10}},{{-100,30}}}})));
    Modelica.Blocks.Interfaces.RealInput from_TES "来自 TES 包层提取进料 (g/h 纯氚当量)"
      annotation(Placement(transformation(extent={{{{-120,-20}},{{-100,0}}}})));
    Modelica.Blocks.Interfaces.RealInput from_WDS "来自 WDS 水除氚浓缩进料 (g/h 纯氚当量)"
      annotation(Placement(transformation(extent={{{{-120,-50}},{{-100,-30}}}})));

    Modelica.Blocks.Interfaces.RealOutput to_SDS "输出至 SDS 储氚系统的高纯燃料 (g/h 纯氚)"
      annotation(Placement(transformation(extent={{{{100,30}},{{120,50}}}})));
    Modelica.Blocks.Interfaces.RealOutput to_VDS "向 VDS (通风除氚系统) 的微量渗透泄漏 (g/h)"
      annotation(Placement(transformation(extent={{{{100,-10}},{{120,10}}}})));
    Modelica.Blocks.Interfaces.RealOutput to_Secondary "向二级包容边界 (手套箱/密封室) 的微量泄漏 (g/h)"
      annotation(Placement(transformation(extent={{{{100,-50}},{{120,-30}}}})));

    // 内部宏观状态与核安全审计变量 (与 CFEDR 接口完全对齐)
    Real inventory(unit="g", start = 0) "ISS-O 动态总储氚滞留量 (g)";
    Real inflow(unit="g/h", start = 0) "总进料氚流率 (g/h)";
    Real outflow(unit="g/h", start = 0) "总出料氚流率 (g/h)";
    Real inv_HT(unit="g", start = 0) "HT 分子形态储氚滞留量 (g)";
    Real inv_HTO(unit="g", start = 0) "HTO 分子形态储氚滞留量 (g)";
    Real decay_rate(unit="g/h") "氚放射性衰变损失率 (g/h)";

    // 适配参数 (与 CFEDR 默认兼容)
    parameter Real Epsilon(unit="1") = 1e-4 "微量泄漏率系数";
    parameter Real EtoV(unit="1") = 0.95 "泄漏物分配至 VDS 的比例 (其余进入二级包容)";
    parameter Real Decay(unit="1/h") = 6.42e-6 "氚衰变常数 (1/h)";
    parameter Real T(unit="h") = 6.0 "水力学特征时间常数 (h)";
    parameter Real Threshold(unit="g") = 20 "门限阈值 (兼容 CFEDR)";

    // 实例化 6 组分机理核心
    Generic_ISS.ISS_O_Core core;

    final parameter Real MW_T = {mw_t_atom:.6f};
    final parameter Real MW_D = {mw_d_atom:.6f};
    final parameter Real MW_H = {mw_h_atom:.6f};
    final parameter Real MW[6] = {{{mw_h2:.5f}, {mw_hd:.5f}, {mw_ht:.5f}, {mw_d2:.5f}, {mw_dt:.5f}, {mw_t2:.5f}}};

    Real m_T_wds, n_wds_T, n_wds_tot;
    Real m_T_tes, n_tes_T, n_tes_tot;

  equation
    // 1. WDS 进料适配 (进 CD1): 氢同位素载体中微量氚提取 (a_H ~ 0.99, a_T ~ 0.01 工程假设)
    m_T_wds = max(0.0, from_WDS);
    n_wds_T = m_T_wds / MW_T;
    n_wds_tot = 100.0 * n_wds_T;

    core.feed_WDS[1] = 0.5 * n_wds_tot * (0.99 * 0.99) * MW[1];
    core.feed_WDS[2] = 0.0;
    core.feed_WDS[3] = n_wds_tot * (0.99 * 0.01) * MW[3];
    core.feed_WDS[4] = 0.0;
    core.feed_WDS[5] = 0.0;
    core.feed_WDS[6] = 0.5 * n_wds_tot * (0.01 * 0.01) * MW[6];

    // 2. TES + CPS 进料适配 (进 CD2): TES 载气提纯
    m_T_tes = max(0.0, from_TES + from_CPS_PFC + from_CPS_BZ);
    n_tes_T = m_T_tes / MW_T;
    n_tes_tot = 100.0 * n_tes_T;

    core.feed_TES[1] = 0.5 * n_tes_tot * (0.99 * 0.99) * MW[1];
    core.feed_TES[2] = 0.0;
    core.feed_TES[3] = n_tes_tot * (0.99 * 0.01) * MW[3];
    core.feed_TES[4] = 0.0;
    core.feed_TES[5] = 0.0;
    core.feed_TES[6] = 0.5 * n_tes_tot * (0.01 * 0.01) * MW[6];

    // 3. 出料适配 (6D -> 1D 纯氚质量流量折算)
    to_SDS = core.prod_T2_SDS[3]*(MW_T/MW[3]) + core.prod_T2_SDS[5]*(MW_T/MW[5]) + core.prod_T2_SDS[6];

    inflow = from_CPS_PFC + from_CPS_BZ + from_TES + from_WDS;
    outflow = to_SDS;

    // 4. 3-Level Confinement 动态泄漏与安全审计
    to_VDS = Epsilon * EtoV * outflow;
    to_Secondary = Epsilon * (1.0 - EtoV) * outflow;

    // 5. 内部动态盘存与物性
    inventory = core.inventory_T;
    inv_HT = core.total_inventory[3]*(MW_T/MW[3]);
    inv_HTO = 0.0;
    decay_rate = inventory * Decay;
  end ISS_O_3LC_Adapter;
'''

    if adapter_mode == "5d":
        body = code_5d
        desc = "Multi-Component 5D/6D Adapters for Generic_ISS Hydrogen Isotope Separation System"
    elif adapter_mode == "3lc":
        body = code_3lc
        desc = "3-Level Confinement (3LC) Adapters for Generic_ISS in CFEDR_3LC"
    else:
        body = code_5d + "\n\n" + code_3lc
        desc = "Multi-Component and 3LC Adapters for Generic_ISS Hydrogen Isotope Separation System"

    return f'''\
package Generic_ISS_Adapters
  "{desc}"

{body}
end Generic_ISS_Adapters;
'''



def generate_column_override_lines(
    col_name: str,
    col_data: dict[str, Any],
    prefix: str = "",
) -> list[str]:
    """Generate override.txt parameter lines for a single column.

    Parameters
    ----------
    col_name : str
        Name of the column (e.g. "CD1").
    col_data : dict
        Column results dictionary containing "actual_results".
    prefix : str
        Optional hierarchical model prefix (e.g. "o_iss").

    Returns
    -------
    list[str]
        Lines for override.txt.
    """
    actual = col_data.get("actual_results", col_data)
    top_flow_mol_h = float(actual["top_flow_mol_h"])
    bot_flow_mol_h = float(actual["bottom_flow_mol_h"])
    top_comp = actual["top_composition"]
    bot_comp = actual["bottom_composition"]

    temps = actual.get("temperatures", {})
    T_top = float(temps.get("top_K", 20.0))
    T_bot = float(temps.get("bottom_K", 25.0))

    m_top = [
        max(0.0, float(top_comp.get(sp, 0.0)) * top_flow_mol_h * SPECIES[sp].molar_mass)
        for sp in SPECIES_ORDER
    ]
    m_bot = [
        max(0.0, float(bot_comp.get(sp, 0.0)) * bot_flow_mol_h * SPECIES[sp].molar_mass)
        for sp in SPECIES_ORDER
    ]

    # Filter out numerical noise to prevent artificial separation factors (e.g., SF=1.0 when bot=0)
    # 1e-6 g/h is roughly 1ug/h, which is well below any physically meaningful flow for isotope routing
    m_top = [m if m >= 1e-6 else 0.0 for m in m_top]
    m_bot = [m if m >= 1e-6 else 0.0 for m in m_bot]

    # Inventory calculation for tau
    inv = actual.get("inventory", {})
    total_inv_grams = float(inv.get("total_grams", 0.0))
    total_feed_g_h = sum(m_top) + sum(m_bot)
    tau = total_inv_grams / max(total_feed_g_h, 1e-4) if total_inv_grams > 0 else 1.0

    p_prefix = f"{prefix}.{col_name}" if prefix else col_name
    lines = [
        f"// --- {p_prefix} Parameters ---",
        f"{p_prefix}.T_top={T_top:.4f}",
        f"{p_prefix}.T_bottom={T_bot:.4f}",
        f"{p_prefix}.tau={tau:.6f}",
    ]
    for i in range(6):
        lines.append(f"{p_prefix}.m_top_ref[{i + 1}]={m_top[i]:.8e}")
    for i in range(6):
        lines.append(f"{p_prefix}.m_bottom_ref[{i + 1}]={m_bot[i]:.8e}")

    return lines


def generate_override_from_results(results_data: dict[str, Any], prefix: str = "") -> str:
    """Generate override.txt content from benchmark/solver results dict."""
    lines = [
        "// Auto-generated override parameters by h2iso",
        "// Target: Generic_ISS Modelica Models",
        "",
    ]
    columns = results_data.get("columns", results_data)
    for col_name, col_data in columns.items():
        if isinstance(col_data, dict):
            lines.extend(generate_column_override_lines(col_name, col_data, prefix=prefix))
            lines.append("")

    return "\n".join(lines)


def generate_cycle_override_file(
    issi_results: dict[str, Any],
    isso_results: dict[str, Any],
    o_iss_prefix: str = "o_iss.core",
    i_iss_prefix: str = "i_iss.core",
) -> str:
    """Generate override.txt for the full plant Cycle model integrating both ISS-I and ISS-O."""
    lines = [
        "// Auto-generated full-cycle override parameters by h2iso",
        "// Target: example_model.Cycle with Generic_ISS_Adapters",
        "",
    ]
    if isso_results:
        lines.append("// ==================== O-ISS (ISS-O) Parameters ====================")
        lines.append(generate_override_from_results(isso_results, prefix=o_iss_prefix))
        lines.append("")
    if issi_results:
        lines.append("// ==================== I-ISS (ISS-I) Parameters ====================")
        lines.append(generate_override_from_results(issi_results, prefix=i_iss_prefix))
        lines.append("")
    return "\n".join(lines)


def export_modelica_package(output_dir: str | Path) -> dict[str, Path]:
    """Export Generic_ISS.mo, Generic_ISS_Adapters.mo and standard override files.

    Parameters
    ----------
    output_dir : str or Path
        Target directory to write files.

    Returns
    -------
    dict[str, Path]
        Paths of generated files.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1. Pure Modelica core package
    mo_core_path = out / "Generic_ISS.mo"
    mo_core_path.write_text(generate_generic_iss_mo(), encoding="utf-8")

    # 2. Multi-component adapter package
    mo_adapter_path = out / "Generic_ISS_Adapters.mo"
    mo_adapter_path.write_text(generate_iss_adapters_mo(), encoding="utf-8")

    result_paths = {
        "Generic_ISS.mo": mo_core_path,
        "Generic_ISS_Adapters.mo": mo_adapter_path,
    }

    # 3. Try loading standard fixtures if available
    fixtures_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "wang2022"
    if fixtures_dir.exists():
        issi_json = fixtures_dir / "wang2022_issi_results.json"
        isso_json = fixtures_dir / "wang2022_isso_results.json"
        issi_data = None
        isso_data = None

        if issi_json.exists():
            with open(issi_json, encoding="utf-8") as f:
                issi_data = json.load(f)
            issi_override_path = out / "override_issi.txt"
            issi_override_path.write_text(
                generate_override_from_results(issi_data), encoding="utf-8"
            )
            result_paths["override_issi.txt"] = issi_override_path

        if isso_json.exists():
            with open(isso_json, encoding="utf-8") as f:
                isso_data = json.load(f)
            isso_override_path = out / "override_isso.txt"
            isso_override_path.write_text(
                generate_override_from_results(isso_data), encoding="utf-8"
            )
            result_paths["override_isso.txt"] = isso_override_path

        if issi_data and isso_data:
            cycle_override_path = out / "override_cycle.txt"
            cycle_override_path.write_text(
                generate_cycle_override_file(issi_data, isso_data), encoding="utf-8"
            )
            result_paths["override_cycle.txt"] = cycle_override_path

    return result_paths
