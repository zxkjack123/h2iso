package CFEDR_3LC "CFEDR 2870 MW model with explicit three-level tritium confinement"
  record Baseline "Baseline Operating Parameters for CFEDR"
    // 聚变功率（Fusion Power）
    constant Real Power(unit="MW") = 2870 "Nominal fusion power output";
    // 燃烧分数（Burning Fraction）
    constant Real BF(unit="1") = 0.05 "Burning fraction: fraction of fuel ions that undergo fusion per pass";
    // 氚增殖比（Tritium Breeding Ratio）
    // [v5.1 M.5 Strategy D] changed from constant to parameter to enable TBR_net override
    // UQ range per v5.md §7.5: Uniform [1.02, 1.12] envelope of 1.02/1.06/1.10/1.12 reference points
    parameter Real TBR(unit="1") = 1.1 "Tritium Breeding Ratio: ratio of tritium produced to tritium consumed; UQ range [1.02, 1.12]";
  end Baseline;

  record Constants "Physical and engineering constants (centralized, eliminates magic numbers per v3.0 §I.0.5/T2.1)"
    constant Real Lambda_T(unit="1/h") = 6.42e-6 "Tritium decay constant per hour (T1/2 = 12.32 yr → ln2/(12.32*8760))";
    constant Real Bq_per_g_T(unit="Bq/g") = 3.56e14 "Specific activity of pure tritium (NIST)";
    constant Real Hours_per_year(unit="h") = 8760 "Hours in nominal year (365 d × 24 h)";
    constant Real DCF_HT(unit="Sv.Bq-1") = 1.8e-15 "Dose Conversion Factor for HT (inhalation, ICRP 71)";
    constant Real DCF_HTO(unit="Sv.Bq-1") = 1.8e-11 "Dose Conversion Factor for HTO (inhalation, ICRP 71; 10000× HT)";
  end Constants;

  // [v3.0 T2.3] TritiumStream connector — Sprint 0.5 PoC freeze
  // Provides typed multi-species tritium flow port. Defined here so downstream
  // upgrades (T3.1 HT/HTO/Qorg split) can populate fields incrementally.
  // Sign convention: producer.outlet.m_X is negative; consumer.inlet.m_X positive.
  // [v3.0 T3.1] TritiumStream connector — upgraded with species mass flows + mol fraction
  connector TritiumStream "Multi-species tritium mass flow (HT + HTO + Qorg)"
    flow Real mdot_HT(unit="g/h") "HT mass flow rate";
    flow Real mdot_HTO(unit="g/h") "HTO mass flow rate";
    flow Real mdot_Qorg(unit="g/h") "organic-Q mass flow rate";
    Real x_HTO(unit="1") "HTO mol fraction in tritium stream (0..1)";
    Real T_carrier(unit="K") "carrier gas/liquid temperature";
    Real m_carrier(unit="kg/h") "carrier mass flow rate";
  end TritiumStream;

  block AccidentTrigger "Smooth accident time-window signal generator (pure time-dependent, no state coupling)"
    parameter Real t_trigger(unit="h") = 1e10 "Accident trigger time (default: never)";
    parameter Real dt_window(unit="h") = 1.0  "Accident duration window";
    Modelica.Blocks.Interfaces.RealOutput trigger "0..1 smooth activation signal";
  equation
    trigger = 0.5*(1 + tanh(200*(time - t_trigger)))
            * 0.5*(1 + tanh(200*(t_trigger + dt_window - time)));
    annotation(uses(Modelica(version = "4.0.0")));
  end AccidentTrigger;

  model FW "First Wall"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    // [v3.0 T2.2] W structural mobile+trapped diagnostic split
    Real inv_W_mobile(unit="g", start = 0);
    Real inv_W_trapped(unit="g", start = 0);
    Real inv_W_total(unit="g") "alias = inv_W_mobile + inv_W_trapped";
    parameter Real k_trap(unit="1/h") = 1e-3 "W trap rate (Hatano 2013 mid)";
    parameter Real k_detrap(unit="1/h") = 1e-5 "W detrap rate";
    parameter Real c_trap_max(unit="g") = 100 "trap saturation capacity";
    parameter Real phi_dpa(unit="1/h") = 1e-7 "dpa-driven trap source modifier";
    parameter Real k_W_uptake(unit="1/h") = 1e-6
      "W structural permeation uptake coefficient: fraction of main inventory entering W_mobile per hour (Hatano 2013 scaling)";
    parameter Real T(unit="h") = 0.28;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4
      "Non-radioactive loss fraction: W armor outgassing + seal leaks (same order as PS/TEP)";
    parameter Real Threshold(unit="g") = 10;
    parameter Real Trap_fraction(unit = "1") = 0.001
      "FW outflow fraction retained in solid waste";
    parameter Real Dust_capture_fraction(unit = "1") = 1e-5
      "FW outflow fraction captured by dust inventory";
    Modelica.Blocks.Interfaces.RealInput from_plasma annotation(
      Placement(transformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}}), iconTransformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}})));
    Modelica.Blocks.Interfaces.RealOutput to_coolant annotation(
      Placement(transformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}})));
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
    Modelica.Blocks.Interfaces.RealOutput to_solid_waste;
    Modelica.Blocks.Interfaces.RealOutput to_dust;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v4.0] Accident response: FW self-contained LOFA/LOVA physics
    Modelica.Blocks.Interfaces.RealInput lofa_trigger "LOFA activation signal (0..1)";
    Modelica.Blocks.Interfaces.RealInput lova_trigger "LOVA activation signal (0..1)";
    parameter Real LOFA_outgas_rate(unit="1/h") = 0.01
      "Enhanced outgassing rate during LOFA (temperature excursion)";
    parameter Real LOVA_release_rate(unit="1/h") = 5.0
      "In-vessel release rate during LOVA (rapid HT→HTO conversion)";
  equation
    inflow = from_plasma;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
  to_coolant = (1 - Trap_fraction - Dust_capture_fraction)*outflow;
  to_solid_waste = Trap_fraction*outflow;
  to_dust = Dust_capture_fraction*outflow;
  // Normal epsilon leak + self-contained accident response (LOFA outgassing + LOVA release)
  to_Secondary = (if inventory > Threshold then Epsilon*outflow else Epsilon*(inventory/T))
               + lofa_trigger * LOFA_outgas_rate * inventory
               + lova_trigger * LOVA_release_rate * inventory;
    // [v3.0 T2.2] mobile+trapped diagnostic ODEs (parallel, no flow coupling to trunk)
    // [v5.7] FIX: uses k_W_uptake*inventory instead of full inflow — prevents phantom mass creation
    der(inv_W_mobile) = k_W_uptake*inventory - k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - Constants.Lambda_T*inv_W_mobile;
    der(inv_W_trapped) = k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - k_detrap*inv_W_trapped - Constants.Lambda_T*inv_W_trapped;
    inv_W_total = inv_W_mobile + inv_W_trapped;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay + inv_W_mobile * Constants.Lambda_T + inv_W_trapped * Constants.Lambda_T;
    annotation(
      Diagram,
      Icon(graphics = {Rectangle(fillColor = {173, 216, 230}, fillPattern = FillPattern.Solid, extent = {{-100, 100}, {100, -100}}), Text(extent = {{-100, 100}, {100, -100}}, textString = "First
Wall", fontName = "Arial")}),
      uses(Modelica(version = "4.0.0")));
  end FW;

  model DIV "Divertor"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    // [v3.0 T2.2] W structural mobile+trapped diagnostic split
    Real inv_W_mobile(unit="g", start = 0);
    Real inv_W_trapped(unit="g", start = 0);
    Real inv_W_total(unit="g") "alias = inv_W_mobile + inv_W_trapped";
    parameter Real k_trap(unit="1/h") = 1e-3 "W trap rate (Hatano 2013 mid)";
    parameter Real k_detrap(unit="1/h") = 1e-5 "W detrap rate";
    parameter Real c_trap_max(unit="g") = 100 "trap saturation capacity";
    parameter Real phi_dpa(unit="1/h") = 1e-7 "dpa-driven trap source modifier";
    parameter Real k_W_uptake(unit="1/h") = 1e-5
      "W structural permeation uptake coefficient: DIV at higher temp/particle flux than FW (Hatano 2013)";
    parameter Real T(unit="h") = 0.28;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 2e-4
      "Non-radioactive loss fraction: higher than FW due to greater particle flux and thermal load on W mono-block";
    parameter Real Threshold(unit="g") = 10;
    parameter Real Trap_fraction(unit = "1") = 0.002
      "DIV outflow fraction retained in solid waste";
    parameter Real Dust_capture_fraction(unit = "1") = 5e-5
      "DIV outflow fraction captured by dust inventory";
    Modelica.Blocks.Interfaces.RealInput from_plasma annotation(
      Placement(transformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}}), iconTransformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}})));
    Modelica.Blocks.Interfaces.RealOutput to_coolant annotation(
      Placement(transformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}})));
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
    Modelica.Blocks.Interfaces.RealOutput to_solid_waste;
    Modelica.Blocks.Interfaces.RealOutput to_dust;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v4.0] Accident response: DIV self-contained LOFA/LOVA physics
    Modelica.Blocks.Interfaces.RealInput lofa_trigger "LOFA activation signal (0..1)";
    Modelica.Blocks.Interfaces.RealInput lova_trigger "LOVA activation signal (0..1)";
    parameter Real LOFA_outgas_rate(unit="1/h") = 0.01
      "Enhanced outgassing rate during LOFA";
    parameter Real LOVA_release_rate(unit="1/h") = 5.0
      "In-vessel release rate during LOVA";
  equation
    inflow = from_plasma;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
  to_coolant = (1 - Trap_fraction - Dust_capture_fraction)*outflow;
  to_solid_waste = Trap_fraction*outflow;
  to_dust = Dust_capture_fraction*outflow;
  // Normal epsilon leak + self-contained accident response
  to_Secondary = (if inventory > Threshold then Epsilon*outflow else Epsilon*(inventory/T))
               + lofa_trigger * LOFA_outgas_rate * inventory
               + lova_trigger * LOVA_release_rate * inventory;
    // [v3.0 T2.2] mobile+trapped diagnostic ODEs (parallel)
    // [v5.7] FIX: uses k_W_uptake*inventory instead of inflow as W source
    der(inv_W_mobile) = k_W_uptake*inventory - k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - Constants.Lambda_T*inv_W_mobile;
    der(inv_W_trapped) = k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - k_detrap*inv_W_trapped - Constants.Lambda_T*inv_W_trapped;
    inv_W_total = inv_W_mobile + inv_W_trapped;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay + inv_W_mobile * Constants.Lambda_T + inv_W_trapped * Constants.Lambda_T;
    annotation(
      Diagram,
      Icon(graphics = {Rectangle(fillColor = {255, 182, 193}, fillPattern = FillPattern.Solid, extent = {{-100, 100}, {100, -100}}), Text(extent = {{-100, 100}, {100, -100}}, textString = "Divertor", fontName = "Arial")}),
      uses(Modelica(version = "4.0.0")));
  end DIV;

  model BZ "Breeding Zone"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    // [v3.0 T2.2] W structural mobile+trapped diagnostic split (BZ structure includes W back-plate)
    Real inv_W_mobile(unit="g", start = 0);
    Real inv_W_trapped(unit="g", start = 0);
    Real inv_W_total(unit="g") "alias = inv_W_mobile + inv_W_trapped";
    parameter Real k_trap(unit="1/h") = 1e-4 "BZ structural trap rate (lower than FW/DIV)";
    parameter Real k_detrap(unit="1/h") = 1e-5 "detrap rate";
    parameter Real c_trap_max(unit="g") = 200 "trap saturation capacity";
    parameter Real phi_dpa(unit="1/h") = 1e-8 "dpa-driven modifier";
    parameter Real k_W_uptake(unit="1/h") = 1e-7
      "W structural permeation uptake: BZ back-plate at lower temp → slower permeation than PFC components";
    parameter Real T(unit="h") = 24;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 0;
    parameter Real Threshold(unit="g") = 0;
    parameter Real TBR(unit="1") = 1.1 "Tritium Breeding Rate";
    parameter Real Fraction_to_Coolant(unit="1") = 0.0005 "Fraction of outflow to Coolant_S_CO2 (structural SiC barrier, PRF=100 baseline; sensitivity sweep: PRF=1000→0.0001, PRF=50→0.001)";
    // [v5.1 M.4 Strategy E] DD-phase Li(n,a)T breeding compensation term
    parameter Real t_DD_end(unit="h") = 2160 "End time of DD phase (3 months)";
    parameter Real P_DD(unit="MW") = 10 "DD-phase fusion power";
    parameter Real k_DD_direct(unit="g/(h.MW)") = 0.01542 "DD direct T production coefficient (v5.1 corrected)";
    parameter Real TBR_DD(unit="1") = 0.4 "Effective TBR during DD phase";
    Real DD_T_gen_breed(unit="g/h");
    Modelica.Blocks.Interfaces.RealOutput to_TES annotation(
      Placement(transformation(origin = {110, 20}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {0, -110}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
    Modelica.Blocks.Interfaces.RealOutput to_coolant annotation(
      Placement(transformation(origin = {110, -20}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {-110, 0}, extent = {{-10, -10}, {10, 10}}, rotation = 180)));
    Modelica.Blocks.Interfaces.RealOutput to_solid_waste;
    Modelica.Blocks.Interfaces.RealInput pulse annotation(
      Placement(transformation(origin = {-124, 0}, extent = {{-20, -20}, {20, 20}}), iconTransformation(origin = {0, 120}, extent = {{-20, -20}, {20, 20}}, rotation = -90)));
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor (alias of T_decay_loss_rate_BZ)";
    // === [v5.7] Tritium audit diagnostics: breeding · recycling · retention ===
    // Breeding breakdown (all rates in g/h)
    Real T_breed_DT(unit="g/h") "Net new T from DT neutron breeding: (TBR-1)*pulse (above burn-replacement)";
    Real T_breed_total_BZ(unit="g/h") "Total new T bred in blanket = T_breed_DT + T_breed_DD (net + compensation)";
    // Feed/recycle distinction (g/h)
    Real T_recycle_feed(unit="g/h") "Recycled T entering BZ to replace burned T (= pulse in DT phase)";
    Real T_throughput_total(unit="g/h") "Total T flux through BZ = recycle + breeding = TBR*pulse (= inflow)";
    // Inventory breakdown (g)
    Real T_inv_flowable(unit="g") "Flowable T inventory: breeder/coolant inventory + W_mobile (recoverable via purge/heat)";
    Real T_inv_retained(unit="g") "Retained T inventory: W_trapped (strongly bound, needs bake-out above 1000 K)";
    Real T_inv_total(unit="g") "Total T held in BZ = flowable + retained";
    // Rate diagnostics (g/h)
    Real T_net_retention_rate(unit="g/h") "Net T trapping rate in structure (trap - detrap: positive = building up, negative = releasing)";
    Real T_decay_loss_rate_BZ(unit="g/h") "T decay loss rate from BZ main inventory";
    Real T_to_waste_rate(unit="g/h") "T permanently lost to solid waste stream from BZ";
    // Permeation placeholder: Epsilon=0 in baseline; structure exists for future non-zero sensitivity studies
    Real T_permeation_rate(unit="g/h") "T permeation/leak rate through BZ structure to secondary containment";
    // --- Diagnostics: Cumulative Variables for precise Auditor mass balance ---
    Real cumulative_inflow(unit="g", start = 0, fixed = true) "Precise ODE integral of bz.inflow (TBR*pulse)";
    Real cumulative_DD_T_gen_breed(unit="g", start = 0, fixed = true) "Precise ODE integral of bz.DD_T_gen_breed";
  equation
    // --- Core dynamics (unchanged) ---
    inflow = TBR*pulse;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - to_solid_waste - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - to_solid_waste - inventory*Decay;
      outflow = 0;
    end if;
    to_coolant = Fraction_to_Coolant*outflow;
    DD_T_gen_breed = if time < t_DD_end then P_DD*k_DD_direct*TBR_DD else 0;
    to_solid_waste = 1e-8*inventory;
    to_TES = (1 - Fraction_to_Coolant)*outflow + DD_T_gen_breed;
    // [v3.0 T2.2] mobile+trapped diagnostic ODEs (parallel)
    // [v5.7] FIX: uses k_W_uptake*inventory instead of inflow as W source
    der(inv_W_mobile) = k_W_uptake*inventory - k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - Constants.Lambda_T*inv_W_mobile;
    der(inv_W_trapped) = k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - k_detrap*inv_W_trapped - Constants.Lambda_T*inv_W_trapped;
    inv_W_total = inv_W_mobile + inv_W_trapped;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    // --- [v5.7] BZ tritium audit diagnostic equations ---
    // Breeding breakdown
    T_breed_DT = (TBR - 1)*pulse "Net DT breeding: total bred minus burn replacement";
    T_breed_total_BZ = T_breed_DT + DD_T_gen_breed "Total T introduced by blanket breeding";
    // Feed/recycle accounting
    T_recycle_feed = pulse "Recycled T from cycle to replace burned T";
    T_throughput_total = T_recycle_feed + T_breed_DT "= TBR*pulse = inflow (total BZ throughput)";
    // Inventory classification
    T_inv_flowable = inventory + inv_W_mobile "Flowable = breeder/coolant + mobile structural T";
    T_inv_retained = inv_W_trapped "Retained = trapped in structure, diff. hard to recover";
    T_inv_total = T_inv_flowable + T_inv_retained "Total BZ T = flowable + retained";
    // Rate diagnostics
    T_net_retention_rate = k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - k_detrap*inv_W_trapped;
    T_decay_loss_rate_BZ = inventory*Decay + inv_W_mobile * Constants.Lambda_T + inv_W_trapped * Constants.Lambda_T;
    T_to_waste_rate = to_solid_waste;
    T_permeation_rate = if inventory > Threshold then Epsilon*((inventory - Threshold)/T) else Epsilon*(inventory/T);
    decay_rate = T_decay_loss_rate_BZ;
    // --- Diagnostics ODEs ---
    der(cumulative_inflow) = inflow;
    der(cumulative_DD_T_gen_breed) = DD_T_gen_breed;
    annotation(
      Diagram,
      Icon(graphics = {Rectangle(fillColor = {144, 238, 144}, fillPattern = FillPattern.Solid, extent = {{-100, 100}, {100, -100}}), Text(extent = {{-100, 100}, {100, -100}}, textString = "Blanket", fontName = "Arial")}),
      uses(Modelica(version = "4.0.0")));
  end BZ;

  model Plasma "Plasma"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    // [v3.0 T2.2] PFC-facing W mobile+trapped surrogate (symmetric framework with FW/DIV/BZ)
    Real inv_W_mobile(unit="g", start = 0);
    Real inv_W_trapped(unit="g", start = 0);
    Real inv_W_total(unit="g") "alias = inv_W_mobile + inv_W_trapped";
    parameter Real k_trap(unit="1/h") = 1e-5 "plasma-facing surrogate trap rate (low, hot)";
    parameter Real k_detrap(unit="1/h") = 1e-4 "detrap rate (hot → fast)";
    parameter Real c_trap_max(unit="g") = 10 "PFC surrogate saturation";
    parameter Real phi_dpa(unit="1/h") = 1e-6 "dpa-driven modifier";
    parameter Real k_W_uptake(unit="1/h") = 1e-4
      "W structural permeation uptake: plasma PFC at extreme temp → fastest permeation, but tiny inventory (~1g)";
    parameter Real T(unit="h") = 1/720;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 0;
    parameter Real Fraction_to_FW(unit="1") = 0.01;
    parameter Real Fraction_to_DIV(unit="1") = 0.01;
    parameter Real Burn_Fraction(unit="1") = 0.05;
    parameter Real Fueling_Efficiency(unit="1") = 0.5;
    // [v5.1 M.4 Strategy E] DD-phase direct T production in plasma
    parameter Real t_DD_end(unit="h") = 2160 "End time of DD phase (3 months)";
    parameter Real P_DD(unit="MW") = 10 "DD-phase fusion power";
    parameter Real k_DD_direct(unit="g/(h.MW)") = 0.01542 "DD direct T production coefficient (v5.1 corrected)";
    Real DD_T_gen_direct(unit="g/h");
    Real fueling_demand(unit = "g/h");
    Modelica.Blocks.Interfaces.RealOutput fueling_demand_out "Fueling demand for FS";
    Modelica.Blocks.Interfaces.RealOutput inv_W_mobile_out "For PMI feedback";
    Modelica.Blocks.Interfaces.RealInput from_FS annotation(
      Placement(transformation(origin = {-110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}, rotation = 180)));
    Modelica.Blocks.Interfaces.RealOutput to_FW annotation(
      Placement(transformation(origin = {110, 40}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {-60, 110}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
    Modelica.Blocks.Interfaces.RealOutput to_DIV annotation(
      Placement(transformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {60, 110}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
    Modelica.Blocks.Interfaces.RealOutput to_PS annotation(
      Placement(transformation(origin = {110, -40}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {0, -110}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
    Modelica.Blocks.Interfaces.RealInput pulse annotation(
      Placement(transformation(origin = {-122, 28}, extent = {{-20, -20}, {20, 20}}), iconTransformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}})));
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
    // --- Diagnostics: Cumulative Variables for precise Auditor mass balance ---
    Real cumulative_burn(unit="g", start = 0, fixed = true) "Precise ODE integral of pulse burn rate";
    Real cumulative_DD_T_gen_direct(unit="g", start = 0, fixed = true) "Precise ODE integral of DD_T_gen_direct";
  equation
    fueling_demand = pulse/(Burn_Fraction*Fueling_Efficiency);
    fueling_demand_out = fueling_demand;
    DD_T_gen_direct = if time < t_DD_end then P_DD*k_DD_direct else 0;
    inflow = from_FS + DD_T_gen_direct;
    der(inventory) = inflow - pulse - (1 + Epsilon)*(inventory/T) - inventory*Decay;
    outflow = inventory/T;
    to_FW = Fraction_to_FW*outflow;
    to_DIV = Fraction_to_DIV*outflow;
    to_PS = (1 - Fraction_to_FW - Fraction_to_DIV)*outflow;
    // [v3.0 T2.2] mobile+trapped diagnostic ODEs (parallel surrogate)
    // [v5.7] FIX: uses k_W_uptake*inventory instead of inflow as W source
    der(inv_W_mobile) = k_W_uptake*inventory - k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - Constants.Lambda_T*inv_W_mobile;
    der(inv_W_trapped) = k_trap*(1 - inv_W_trapped/c_trap_max)*inv_W_mobile - k_detrap*inv_W_trapped - Constants.Lambda_T*inv_W_trapped;
    inv_W_total = inv_W_mobile + inv_W_trapped;
    inv_W_mobile_out = inv_W_mobile;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay + inv_W_mobile * Constants.Lambda_T + inv_W_trapped * Constants.Lambda_T;
    // --- Diagnostics ODEs ---
    der(cumulative_burn) = pulse;
    der(cumulative_DD_T_gen_direct) = DD_T_gen_direct;
    annotation(
      Diagram,
      Icon(graphics = {Rectangle(fillColor = {255, 182, 193}, fillPattern = FillPattern.Solid, extent = {{-100, 100}, {100, -100}}), Text(extent = {{-100, 100}, {100, -100}}, textString = "Plasma", fontName = "Arial")}),
      uses(Modelica(version = "4.0.0")));
  end Plasma;

  block Pulse "Generate two identical pulse signals of type Real"
    parameter Real power(unit="MW") = 2870;
    parameter Real amplitude(unit="g/h") = power*6.3935*1e-3 "脉冲幅度，对应1.5GW聚变堆每小时氚消耗";
    parameter Real burn_T(unit="h") = 2.0 "脉冲时间(h)，CFEDR 20MA H-mode flat-top 120 min (Ref: Rui Ding 2nd IAC p.7,p.15; Lei Chen 2nd IAC p.4,p.12)";
    parameter Real width(unit="1", final min = 1e-10, final max = 100) = 90 "脉冲宽度，占周期的百分比";
    parameter Real period(unit="h", final min = 1e-10, start = 480) = burn_T*100/width "一个周期的时间";
    parameter Integer nperiod = -1 "周期数（< 0 表示无限周期）";
    parameter Real startTime(unit="h") = 0 "第一个脉冲的开始时间";
    parameter Real offset(unit="g/h") = 0 "输出信号的偏移量";
    Modelica.Blocks.Interfaces.RealOutput y1 annotation(
      Placement(transformation(origin = {108, 20}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {-110, 0}, extent = {{-10, -10}, {10, 10}}, rotation = 180)));
    Modelica.Blocks.Interfaces.RealOutput y2 annotation(
      Placement(transformation(origin = {106, -40}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}})));
  protected
    Real T_width(unit="h") = period*width/100 "脉冲宽度时间";
  equation
    y1 = offset + (if time < startTime then 0 else if nperiod == 0 then 0 else if nperiod > 0 and floor((time - startTime)/period) > nperiod then 0 else if mod(time - startTime, period) <= T_width then amplitude else 0);
    y2 = y1;
    annotation(
      Icon(coordinateSystem(preserveAspectRatio = true, extent = {{-100, -100}, {100, 100}}), graphics = {Rectangle(extent = {{-100, 100}, {100, -100}}), Text(extent = {{-100, 100}, {100, -100}}, textString = "Pulse")}),
      uses(Modelica(version = "4.0.0")));
  end Pulse;

  model PS "Pump System"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 0.17;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 640;
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_plasma annotation(
      Placement(transformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}}), iconTransformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}})));
    Modelica.Blocks.Interfaces.RealOutput to_tep annotation(
      Placement(transformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}})));
    Modelica.Blocks.Interfaces.RealOutput to_VDS annotation(
      Placement(transformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {100, -100}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
    Modelica.Blocks.Interfaces.RealOutput to_Secondary annotation(
      Placement(transformation(origin = {110, 40}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {100, 80}, extent = {{-10, -10}, {10, 10}})));
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_plasma;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_tep = outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end PS;

  model TEP "Tokamak Exhaust Processing System"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 2;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 0;
    parameter Real DIR(unit="1") = 0.85 "Fraction of outflow directed to SDS";
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_pump annotation(
      Placement(transformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}}), iconTransformation(origin = {-120, 0}, extent = {{-20, -20}, {20, 20}})));
    Modelica.Blocks.Interfaces.RealOutput to_SDS annotation(
      Placement(transformation(origin = {110, 20}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {0, 110}, extent = {{-10, -10}, {10, 10}}, rotation = 90)));
    Modelica.Blocks.Interfaces.RealOutput to_ISS annotation(
      Placement(transformation(origin = {110, -20}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}})));
    Modelica.Blocks.Interfaces.RealOutput to_VDS annotation(
      Placement(transformation(origin = {110, 0}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {100, -100}, extent = {{-10, -10}, {10, 10}}, rotation = -90)));
    Modelica.Blocks.Interfaces.RealOutput to_Secondary annotation(
      Placement(transformation(origin = {110, 60}, extent = {{-10, -10}, {10, 10}}), iconTransformation(origin = {100, 80}, extent = {{-10, -10}, {10, 10}})));
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_pump;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_SDS = DIR*outflow;
    to_ISS = (1 - DIR)*outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end TEP;

  model TES_gas "Tritium Extraction System(gas)"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 21.6;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 0;
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_BZ;
    Modelica.Blocks.Interfaces.RealOutput to_TES;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_BZ;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_TES = outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end TES_gas;

  model TES "Tritium Extraction System (liquid phase)"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 12;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 200;
    parameter Real EtoV(unit="1") = 0.99;
    Modelica.Blocks.Interfaces.RealInput from_TES_gas "Inflow from gas-phase TES_gas (replaces direct BZ connection)";
    Modelica.Blocks.Interfaces.RealOutput to_O_ISS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_TES_gas;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_O_ISS = outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end TES;

  model O_ISS "Outer Isotope Separation System based on Generic_ISS_Adapters"
    extends Generic_ISS_Adapters.ISS_O_3LC_Adapter;
    annotation(uses(Modelica(version = "4.0.0")));
  end O_ISS;

  model WDS "Water Detritiation System"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 48;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 100 "CECE column structural holdup (sensitivity: 50-200g)";
    parameter Real EtoV(unit="1") = 0.99999;
    parameter Real Fraction_to_Liquid(unit="1") = 1e-5
      "Fraction of WDS outflow discharged as liquid effluent (detritiated water with residual T; ITER DF ~1e5)";
    Modelica.Blocks.Interfaces.RealInput from_coolant_FW;
    Modelica.Blocks.Interfaces.RealInput from_coolant_DIV;
    Modelica.Blocks.Interfaces.RealInput from_ISS;
    Modelica.Blocks.Interfaces.RealInput from_VDS;
    Modelica.Blocks.Interfaces.RealInput from_SC "Inflow from Secondary_Containment ADS (3LC extension)";
    Modelica.Blocks.Interfaces.RealInput from_TC "Inflow from Tertiary_Containment HVAC (3LC extension)";
    Modelica.Blocks.Interfaces.RealOutput to_OISS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    Modelica.Blocks.Interfaces.RealOutput to_Liquid_Release
      "Residual tritium in detritiated water effluent";
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_coolant_FW + from_coolant_DIV + from_ISS + from_VDS + from_SC + from_TC;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_OISS = (1 - Fraction_to_Liquid)*outflow;
    to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
    to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    to_Liquid_Release = Fraction_to_Liquid * outflow;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end WDS;

  model Coolant_FW "First Wall Coolant Loop"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 24;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 0;
    parameter Real Fraction_to_CPS_PFC(unit="1") = 0.9999;
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_FW;
    Modelica.Blocks.Interfaces.RealOutput to_CPS_PFC;
    Modelica.Blocks.Interfaces.RealOutput to_WDS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v4.0] Accident response: Coolant_FW self-contained LOCA physics
    Modelica.Blocks.Interfaces.RealInput loca_trigger "LOCA activation signal (0..1)";
    parameter Real LOCA_leak_rate(unit="1/h") = 2.0
      "Coolant inventory leak rate during LOCA (fraction/h released to SC)";
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_FW;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_CPS_PFC = Fraction_to_CPS_PFC*outflow;
    to_WDS = (1 - Fraction_to_CPS_PFC)*outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  // Normal epsilon leak + self-contained LOCA coolant leak
  to_Secondary = (if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T))
               + loca_trigger * LOCA_leak_rate * inventory;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Coolant_FW;

  model Coolant_DIV "Divertor Coolant Loop"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 24;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 0;
    parameter Real Fraction_to_CPS_PFC(unit="1") = 0.9999;
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_DIV;
    Modelica.Blocks.Interfaces.RealInput hx_loss "HX permeation loss removed from DIV coolant inventory";
    Modelica.Blocks.Interfaces.RealOutput to_CPS_PFC;
    Modelica.Blocks.Interfaces.RealOutput to_WDS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    Modelica.Blocks.Interfaces.RealOutput inventory_out;
    // [v4.0] Accident response: Coolant_DIV self-contained LOCA physics
    Modelica.Blocks.Interfaces.RealInput loca_trigger "LOCA activation signal (0..1)";
    parameter Real LOCA_leak_rate(unit="1/h") = 2.0
      "Coolant inventory leak rate during LOCA (fraction/h released to SC)";
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inventory_out = inventory;
    inflow = from_DIV;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - hx_loss - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - hx_loss - inventory*Decay;
      outflow = 0;
    end if;
    to_CPS_PFC = Fraction_to_CPS_PFC*outflow;
    to_WDS = (1 - Fraction_to_CPS_PFC)*outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  // Normal epsilon leak + self-contained LOCA coolant leak
  to_Secondary = (if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T))
               + loca_trigger * LOCA_leak_rate * inventory;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Coolant_DIV;

  model CPS_PFC "Coolant Purification System(PFC)"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 48;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 200;
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_coolant_FW;
    Modelica.Blocks.Interfaces.RealInput from_coolant_DIV;
    Modelica.Blocks.Interfaces.RealOutput to_OISS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_coolant_FW + from_coolant_DIV;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_OISS = outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end CPS_PFC;

  model Coolant_S_CO2 "Supercritical CO2 Coolant Loop"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 24;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 0;
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_BZ;
    Modelica.Blocks.Interfaces.RealInput hx_loss "HX permeation loss removed from sCO2 coolant inventory";
    Modelica.Blocks.Interfaces.RealOutput to_CPS_BZ;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    Modelica.Blocks.Interfaces.RealOutput inventory_out;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inventory_out = inventory;
    inflow = from_BZ;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - hx_loss - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - hx_loss - inventory*Decay;
      outflow = 0;
    end if;
    to_CPS_BZ = outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Coolant_S_CO2;

  model CPS_BZ "Coolant Purification System(BZ)"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 48;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 50 "Gas-phase CPS structural holdup: catalyst bed + molecular sieve (sensitivity: 20-100g)";
    parameter Real EtoV(unit="1") = 0.95;
    Modelica.Blocks.Interfaces.RealInput from_coolant;
    Modelica.Blocks.Interfaces.RealOutput to_OISS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_coolant;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_OISS = outflow;
  to_VDS = if inventory > Threshold then Epsilon*EtoV*outflow else Epsilon*EtoV*(inventory/T);
  to_Secondary = if inventory > Threshold then Epsilon*(1 - EtoV)*outflow else Epsilon*(1 - EtoV)*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end CPS_BZ;

  model I_ISS "Inner Isotope Separation System based on Generic_ISS_Adapters"
    extends Generic_ISS_Adapters.ISS_I_3LC_Adapter;
    annotation(uses(Modelica(version = "4.0.0")));
  end I_ISS;

  model FS "Fueling System"
    Real inventory(unit = "g", start = 0, fixed = true);
    Real inflow(start = 0);
    Real outflow(start = 0);
    parameter Real T = 0.5;
    parameter Real Decay = 6.4e-6;
    parameter Real Epsilon(unit = "1") = 1e-4;
    parameter Real Threshold(unit = "g") = 0;
    parameter Real EtoV(unit = "1") = 0.95;
    parameter Real Refill_T(unit = "h") = 0.05
      "First-order refill time constant used to keep the fueling buffer near the demand-based target";
    Real target_inventory(unit = "g");
    Modelica.Blocks.Interfaces.RealInput demand_from_plasma;
    Modelica.Blocks.Interfaces.RealOutput to_plasma;
    Modelica.Blocks.Interfaces.RealOutput from_SDS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    target_inventory = demand_from_plasma*T;
    outflow = demand_from_plasma;
    inflow = outflow + Epsilon*outflow + inventory*Decay + (target_inventory - inventory)/Refill_T;
    der(inventory) = inflow - (1 + Epsilon)*outflow - inventory*Decay;
    from_SDS = inflow;
  to_plasma = outflow;
  to_VDS = Epsilon*EtoV*outflow;
  to_Secondary = Epsilon*(1 - EtoV)*outflow;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end FS;

  model SDS "Storage and Delivery System"
    Real inventory(unit="g", start = 6100, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    Real der_sds(unit="g/h", start = 0);
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real EtoV(unit="1") = 0.99;
    parameter Real DoubleInventory(unit="g") = 12200;
    Modelica.Blocks.Interfaces.RealInput from_ISS;
    Modelica.Blocks.Interfaces.RealInput from_OISS;
    Modelica.Blocks.Interfaces.RealInput from_TEP;
    Modelica.Blocks.Interfaces.RealInput to_FS;
    Modelica.Blocks.Interfaces.RealOutput to_VDS;
    Modelica.Blocks.Interfaces.RealOutput to_Secondary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_ISS + from_OISS + from_TEP;
    outflow = to_FS;
    der_sds = inflow - (1 + Epsilon)*outflow - inventory*Decay;
    der(inventory) = inflow - (1 + Epsilon)*outflow - inventory*Decay;
    to_VDS = Epsilon*EtoV*outflow;
    to_Secondary = Epsilon*(1 - EtoV)*outflow;
    when inventory >= DoubleInventory then
      terminate("库存已倍增，停止模拟");
    end when;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end SDS;

  model Secondary_Containment "Level-2 Confinement: Gloveboxes & Sealed Rooms"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 2 "Level-2 ADS residence time (h), ITER local DS: 1-4h";
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Leak_to_L3(unit="1/h") = 0.001
      "Hourly leak fraction to Level-3 building, ITER glovebox spec <0.1%vol/h";
    parameter Real Threshold(unit="g") = 0;
    Modelica.Blocks.Interfaces.RealInput from_PS;
    Modelica.Blocks.Interfaces.RealInput from_FW;
    Modelica.Blocks.Interfaces.RealInput from_DIV;
    Modelica.Blocks.Interfaces.RealInput from_TEP;
    Modelica.Blocks.Interfaces.RealInput from_TES_gas;
    Modelica.Blocks.Interfaces.RealInput from_TES;
    Modelica.Blocks.Interfaces.RealInput from_O_ISS;
    Modelica.Blocks.Interfaces.RealInput from_WDS;
    Modelica.Blocks.Interfaces.RealInput from_Coolant_FW;
    Modelica.Blocks.Interfaces.RealInput from_Coolant_DIV;
    Modelica.Blocks.Interfaces.RealInput from_CPS_PFC;
    Modelica.Blocks.Interfaces.RealInput from_Coolant_sCO2;
    Modelica.Blocks.Interfaces.RealInput from_CPS_BZ;
    Modelica.Blocks.Interfaces.RealInput from_I_ISS;
    Modelica.Blocks.Interfaces.RealInput from_FS;
    Modelica.Blocks.Interfaces.RealInput from_SDS;
    Modelica.Blocks.Interfaces.RealInput from_Dust
      "LOCA-event mobilized dust-borne tritium (0 in steady-state baseline)";
    // [v4.0] from_Accident removed: accident flows now arrive via each component's to_Secondary
    Modelica.Blocks.Interfaces.RealOutput to_WDS;
    Modelica.Blocks.Interfaces.RealOutput to_Tertiary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
    // [v3.0 T3.2] N6 oxidation kinetics (Bekris 2014, Glugla 2006)
    parameter Real k0_ox(unit="m3/(mol.h)") = 1e-3 "Oxidation pre-exponential factor (Bekris 2014: k0~1e-3 for HT+O2->HTO on steel)";
    parameter Real Ea_ox(unit="J/mol") = 80e3 "Activation energy for HT oxidation (Bekris 2014: 70-90 kJ/mol range)";
    parameter Real O2_conc(unit="mol/m3") = 8.3
      "O2 concentration in containment air (ambient: 21% × 101325 Pa / (8.314×293) ≈ 8.7 mol/m3)";
    parameter Real T_room(unit="K") = 293.15
      "Containment air temperature for oxidation kinetics";
    Real r_ox(unit="g/h") "HT→HTO oxidation rate";
  equation
    inflow = from_PS + from_FW + from_DIV + from_TEP + from_TES_gas + from_TES + from_O_ISS + from_WDS
           + from_Coolant_FW + from_Coolant_DIV + from_CPS_PFC + from_Coolant_sCO2
           + from_CPS_BZ + from_I_ISS + from_FS + from_SDS + from_Dust;
    if inventory > Threshold then
      der(inventory) = inflow - outflow - Leak_to_L3*inventory - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Leak_to_L3*inventory - inventory*Decay;
      outflow = 0;
    end if;
    to_WDS = outflow;
    to_Tertiary = Leak_to_L3*inventory;
    r_ox = k0_ox * Modelica.Math.exp(-Ea_ox / (8.314 * T_room)) * inv_HT * O2_conc;
    der(inv_HTO) = r_ox - Leak_to_L3*inv_HTO - (if inventory > 1e-20 then outflow*(inv_HTO/inventory) else 0) - inv_HTO*Decay;
    inv_HT = inventory - inv_HTO;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Secondary_Containment;

  model Tertiary_Containment "Level-3 Confinement: Reactor Building Envelope"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real DF(unit="1") = 1000
      "Building ADS decontamination factor (ITER HVAC: 1000-10000 for HTO)";
    parameter Real Ventilation_rate(unit="1/h") = 1.0
      "Building filtered air exchange rate";
    Modelica.Blocks.Interfaces.RealInput from_Secondary;
    Modelica.Blocks.Interfaces.RealInput from_Maintenance;
    Modelica.Blocks.Interfaces.RealInput from_VDS
      "VDS processed exhaust (detritiated gas with residual T at 1/DF_VDS level)";
    Modelica.Blocks.Interfaces.RealOutput to_WDS;
    Modelica.Blocks.Interfaces.RealOutput to_Stack;
    // [v3.0 T3.1] HT/HTO species decomposition
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
    // [v3.0 T3.2] N6 oxidation kinetics (Bekris 2014, Glugla 2006)
    parameter Real k0_ox(unit="m3/(mol.h)") = 1e-3 "Oxidation pre-exponential factor (Bekris 2014: k0~1e-3 for HT+O2->HTO on steel)";
    parameter Real Ea_ox(unit="J/mol") = 80e3 "Activation energy for HT oxidation (Bekris 2014: 70-90 kJ/mol range)";
    parameter Real O2_conc(unit="mol/m3") = 8.3
      "O2 concentration in containment air";
    parameter Real T_room(unit="K") = 293.15
      "Containment air temperature for oxidation kinetics";
    Real r_ox(unit="g/h") "HT→HTO oxidation rate";
  equation
    inflow = from_Secondary + from_Maintenance + from_VDS;
    der(inventory) = inflow - Ventilation_rate*inventory - inventory*Decay;
    outflow = Ventilation_rate*inventory;
    to_WDS = outflow*(1 - 1/DF);
    to_Stack = outflow/DF;
    // [v3.0 T3.2] oxidation: HT + O2 → HTO
    r_ox = k0_ox * Modelica.Math.exp(-Ea_ox / (8.314 * T_room)) * inv_HT * O2_conc;
    der(inv_HTO) = r_ox - Ventilation_rate*inv_HTO - inv_HTO*Decay;
    inv_HT = inventory - inv_HTO;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Tertiary_Containment;

  model Stack_Release "Environmental Release Monitor (gaseous + liquid)"
    Real cumulative_release(unit="g", start = 0, fixed = true) "Total gaseous release via stack";
    Real release_rate(unit="g/h");
    parameter Real Annual_Limit(unit="g") = 1.0
      "Annual gaseous tritium release design target (ITER: ~1g/yr ≈ 3.7e14 Bq/yr; CFEDR TBD)";
    Modelica.Blocks.Interfaces.RealInput from_Tertiary;
    Modelica.Blocks.Interfaces.RealInput from_HX;
    Modelica.Blocks.Interfaces.RealInput from_HX_water
      "From DIV water-loop HX permeation";
    Modelica.Blocks.Interfaces.RealOutput cumulative_release_out;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
  equation
    release_rate = from_Tertiary + from_HX + from_HX_water;
    der(cumulative_release) = release_rate;
    cumulative_release_out = cumulative_release;
    when cumulative_release >= Annual_Limit then
      terminate("Annual tritium release limit exceeded");
    end when;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = cumulative_release;
    inv_HTO = 0;
    annotation(uses(Modelica(version = "4.0.0")));
  end Stack_Release;

  model Liquid_Release "Liquid Effluent Tritium Release Monitor"
    Real cumulative_release(unit="g", start = 0, fixed = true) "Total liquid tritium release";
    Real release_rate(unit="g/h");
    parameter Real Annual_Limit_Liquid(unit="g") = 0.1
      "Annual liquid tritium release limit (ITER: ~0.1 g/yr for detritiated water discharge)";
    Modelica.Blocks.Interfaces.RealInput from_WDS
      "Residual tritium in WDS detritiated water effluent";
    Modelica.Blocks.Interfaces.RealOutput cumulative_release_out;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
  equation
    release_rate = from_WDS;
    der(cumulative_release) = release_rate;
    cumulative_release_out = cumulative_release;
    when cumulative_release >= Annual_Limit_Liquid then
      terminate("Annual liquid tritium release limit exceeded");
    end when;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = cumulative_release;
    inv_HTO = 0;
    annotation(uses(Modelica(version = "4.0.0")));
  end Liquid_Release;

  model Dose_Estimator "Public dose estimation from tritium releases (single-direction sink)"
    // Inputs: cumulative releases from Stack and Liquid monitors
    Modelica.Blocks.Interfaces.RealInput stack_cumulative "Cumulative gaseous release via stack (g)";
    Modelica.Blocks.Interfaces.RealInput liquid_cumulative "Cumulative liquid effluent release (g)";
    // Parameters: site-specific atmospheric dispersion
    parameter Real chi_over_Q(unit="s/m3") = 5e-6
      "Annual average atmospheric dispersion factor at site boundary (ITER reference: 5e-6 s/m3)";
    parameter Real BR(unit="m3/s") = 2.32e-4
      "Reference adult breathing rate (ICRP 66, annual average)";
    // Output: dose from actual cumulative releases (read at t=8760 for annual value)
    Real annual_dose_uSv(unit="uSv/y") "Public dose from cumulative releases";
    // Intermediate: total activities released
    Real HT_release_Bq(unit="Bq") "Cumulative HT release activity (stack, gaseous)";
    Real HTO_release_Bq(unit="Bq") "Cumulative HTO release activity (liquid effluent)";
  equation
    // Stack (gaseous) release → conservatively all HT
    HT_release_Bq = stack_cumulative * Constants.Bq_per_g_T;
    // Liquid effluent → conservatively all HTO (water form)
    HTO_release_Bq = liquid_cumulative * Constants.Bq_per_g_T;
    // Dose: Release × dispersion × breathing → intake; intake × DCF → dose
    // dose_Sv = (HT_Bq * DCF_HT + HTO_Bq * DCF_HTO) * chi/Q * BR
    annual_dose_uSv = (HT_release_Bq * Constants.DCF_HT + HTO_release_Bq * Constants.DCF_HTO) * chi_over_Q * BR * 1e6;
    annotation(uses(Modelica(version = "4.0.0")));
  end Dose_Estimator;

  model HX_Permeation "HX Tritium Permeation to Power Conversion Side (S-CO2 loop)"
    Real inventory(unit="g", start = 0, fixed = true);
    Real permeation_flux(unit="g/h", start = 0);
    parameter Real k_Henry(unit="1/h") = 1e-5
      "Linear effective permeation coefficient (driving = coolant inventory)";
    parameter Real PRF_coating(unit="1") = 100
      "Permeation Reduction Factor from barrier coating (Al2O3/Er2O3)";
    parameter Real T_secondary(unit="h") = 48
      "Secondary side residence time before stack release";
    Modelica.Blocks.Interfaces.RealInput coolant_inventory
      "From Coolant_S_CO2.inventory (linear Henry approximation)";
    Modelica.Blocks.Interfaces.RealOutput to_Stack;
    Modelica.Blocks.Interfaces.RealOutput permeation_flux_out;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
  equation
    permeation_flux = k_Henry/PRF_coating * coolant_inventory;
    permeation_flux_out = permeation_flux;
    der(inventory) = permeation_flux - inventory/T_secondary;
    to_Stack = inventory/T_secondary;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    annotation(uses(Modelica(version = "4.0.0")));
  end HX_Permeation;

  model HX_Permeation_Water "HX Tritium Permeation from DIV Water Cooling Loop"
    Real inventory(unit="g", start = 0, fixed = true);
    Real permeation_flux(unit="g/h", start = 0);
    parameter Real k_perm(unit="1/h") = 5e-6
      "Linear effective permeation coefficient for water/steam loop (lower T, higher H solubility in water partly offset by lower diffusivity through steel)";
    parameter Real PRF_coating(unit="1") = 50
      "PRF for DIV water-loop HX (steel SG tubes, no dedicated tritium barrier; conservative)";
    parameter Real T_secondary(unit="h") = 72
      "Secondary steam side residence time (condenser + feedwater, longer loop than S-CO2 PCS)";
    Modelica.Blocks.Interfaces.RealInput coolant_inventory
      "From Coolant_DIV.inventory";
    Modelica.Blocks.Interfaces.RealOutput to_Stack;
    Modelica.Blocks.Interfaces.RealOutput permeation_flux_out;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
  equation
    permeation_flux = k_perm/PRF_coating * coolant_inventory;
    permeation_flux_out = permeation_flux;
    der(inventory) = permeation_flux - inventory/T_secondary;
    to_Stack = inventory/T_secondary;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    annotation(uses(Modelica(version = "4.0.0")));
  end HX_Permeation_Water;

  model Solid_Waste "Solid Material Tritium Retention (FW/DIV/BZ structures)"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Trap_fraction_FW(unit="1") = 0.001
      "FW outflow fraction trapped in W armor (ion implantation + n damage)";
    parameter Real Trap_fraction_DIV(unit="1") = 0.002
      "DIV outflow fraction trapped in W mono-block (higher flux than FW: ~10 MW/m2 vs ~0.5 MW/m2)";
    parameter Real Trap_fraction_BZ(unit="1/h") = 1e-8
      "BZ inventory fraction trapped per hour in structural materials";
    parameter Real Maintenance_interval(unit="h") = Constants.Hours_per_year "Annual cycle";
    parameter Real Release_fraction(unit="1") = 0.1
      "Fraction of solid inventory released during maintenance (continuous-equivalent)";
    Modelica.Blocks.Interfaces.RealInput from_FW_outflow;
    Modelica.Blocks.Interfaces.RealInput from_DIV_outflow;
    Modelica.Blocks.Interfaces.RealInput from_BZ_outflow;
    Modelica.Blocks.Interfaces.RealInput from_Dust
      "Direct g/h rate of T transferred from dust to solid waste at maintenance";
    Modelica.Blocks.Interfaces.RealOutput to_Tertiary;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    inflow = from_FW_outflow
           + from_DIV_outflow
           + from_BZ_outflow
           + from_Dust;
    der(inventory) = inflow - to_Tertiary - inventory*Decay;
    to_Tertiary = Release_fraction * inventory / Maintenance_interval;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Solid_Waste;

  model Dust_Inventory "In-vessel W dust-borne tritium accumulator (CFEDR all-W PFC; Tier-2.5 safety source-term node)"
    // [v3.0 T4.2] Dust_Inventory inv_mobile: surface-adsorbed, fast-releasable during LOCA
    // [v3.0 T4.2] Dust_Inventory inv_trapped: bulk-diffused in W grains, slow-release (Bekris 2014)
    Real inv_mobile(unit="g", start = 0) "Tritium mobile on dust surface (fast-releasable)";
    Real inv_trapped(unit="g", start = 0) "Tritium trapped in W dust bulk (slow-release, requires >700C)";
    Real inv_dust(unit="g") "Total = inv_mobile + inv_trapped (backward-compat alias)";
    Real dust_mass(unit="g", start = 0) "Cumulative W dust mass in vacuum vessel (irreversible)";
    Real cumulative_to_VDS(unit="g", start = 0, fixed = true) "Lifetime T released from dust to gas/VDS (audit)";
    Real cumulative_to_SW(unit="g", start = 0, fixed = true) "Lifetime T shipped out with dust as solid waste (audit)";
    // Erosion / dust production (unchanged from Counsell 2006)
    parameter Real erosion_rate_FW(unit="g/h") = 0.05
      "FW W dust production rate (~400 g/FPY for CFEDR-2870; Counsell 2006 scaled, W vs C 1/1000)";
    parameter Real erosion_rate_DIV(unit="g/h") = 0.50
      "DIV W dust production rate (~10x FW due to higher heat/particle flux; ~4 kg/FPY)";
    // [v3.0 T4.2] Trapping kinetics (Bekris & Glugla 2014; room-T diffusion into W grain bulk)
    parameter Real k_trap(unit="1/h") = 5e-3
      "Mobile→trapped trapping rate (T diffusion into W grain bulk at ~300K; Bekris 2014 mid-estimate)";
    parameter Real k_detrap(unit="1/h") = 1e-6
      "Trapped→mobile detrapping rate at room-T (negligible; only significant at >700C maintenance)";
    parameter Real c_trap_max(unit="g") = 50
      "Trap saturation capacity (limited by W grain surface area × T solubility at 300K)";
    // Routing fractions
    parameter Real f_resuspend(unit="1/h") = 1e-6
      "Hourly fraction of mobile dust-T resuspended to VDS during normal operation (ITER GSSR assumption)";
    parameter Real T_maintain(unit="h") = Constants.Hours_per_year
      "Annual maintenance characteristic time (>700C vacuum heat desorption per Bekris & Glugla 2014)";
    parameter Real f_desorbed(unit="1") = 0.9
      "Fraction of dust-T released as HT/HTO gas during maintenance heating (Bekris 2014: >90% at >700C)";
    // LOCA mobilization (differentiated by state)
    parameter Real f_loca_mobile(unit="1/h") = 0.5
      "LOCA mobilization rate for surface-mobile T (fast release; 50%/h in steam/air ingress)";
    parameter Real f_loca_trapped(unit="1/h") = 0.01
      "LOCA mobilization rate for bulk-trapped T (slow release; requires thermal pulse)";
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Admin_Limit_dust(unit="g") = 670000
      "ITER administrative limit on tritiated dust on hot surfaces: 670 kg W dust (Taylor 2017 / GSSR)";
    Modelica.Blocks.Interfaces.RealInput from_FW_outflow
      "Actual T capture rate routed from FW into dust inventory";
    Modelica.Blocks.Interfaces.RealInput from_DIV_outflow
      "Actual T capture rate routed from DIV into dust inventory";
    Modelica.Blocks.Interfaces.RealInput loca_trigger "0/1 LOCA event active signal from Cycle_3LC";
    Modelica.Blocks.Interfaces.RealInput from_PMI "Extra T capture rate from PMI feedback (g/h)";
    Modelica.Blocks.Interfaces.RealOutput to_VDS
      "Routine resuspension + maintenance gas-phase release (HT/HTO)";
    Modelica.Blocks.Interfaces.RealOutput to_Solid_Waste
      "Residual T trapped in W dust shipped as solid waste";
    Modelica.Blocks.Interfaces.RealOutput to_Secondary
      "LOCA-event mobilized airborne dust to Secondary Containment (event-only)";
    // Internal: dust release rate (for test observability)
    Real dust_release_rate(unit="g/h") "Total dust mobilization flow to SC during LOCA";
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
    // Dust mass grows monotonically with operation (unchanged)
    der(dust_mass) = erosion_rate_FW + erosion_rate_DIV;
    // Total inventory alias
    inv_dust = inv_mobile + inv_trapped;
    // Outflows: routine from mobile; maintenance from both; LOCA differentiated
    to_VDS = f_resuspend * inv_mobile + f_desorbed/T_maintain * inv_dust;
    to_Solid_Waste = (1 - f_desorbed)/T_maintain * inv_dust;
    dust_release_rate = loca_trigger * (f_loca_mobile * inv_mobile + f_loca_trapped * inv_trapped);
    to_Secondary = dust_release_rate;
  // [v3.0 T4.2] Mobile state: audited PFC dust capture, trapping loss, routine release, LOCA release
  der(inv_mobile) = from_FW_outflow
          + from_DIV_outflow
                    + from_PMI
                    + k_detrap * inv_trapped
                    - k_trap * (1 - inv_trapped/c_trap_max) * inv_mobile
                    - f_resuspend * inv_mobile
                    - (1/T_maintain) * inv_mobile
                    - loca_trigger * f_loca_mobile * inv_mobile
                    - inv_mobile * Decay;
    // [v3.0 T4.2] Trapped state: trapping gain, detrapping loss, maintenance, LOCA slow release
    der(inv_trapped) = k_trap * (1 - inv_trapped/c_trap_max) * inv_mobile
                     - k_detrap * inv_trapped
                     - (1 - f_desorbed)/T_maintain * inv_trapped
                     - f_desorbed/T_maintain * inv_trapped
                     - loca_trigger * f_loca_trapped * inv_trapped
                     - inv_trapped * Decay;
    // Cumulative audit traces
    der(cumulative_to_VDS) = to_VDS;
    der(cumulative_to_SW) = to_Solid_Waste;
    // Administrative limit guard
    when dust_mass >= Admin_Limit_dust then
      terminate("ITER administrative tritiated-dust limit (670 kg W dust) exceeded");
    end when;
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inv_dust;
    inv_HTO = 0;
    decay_rate = inv_mobile * Decay + inv_trapped * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end Dust_Inventory;

  model PMI "Plasma-Material Interaction feedback: high W surface T concentration enhances dust T capture"
    // [v3.0 T4.3] Heuristic model: when plasma inv_W_mobile is high (W surface saturated),
    // extra tritium is captured on dust via co-deposition and implantation into eroded W.
    // dust_rate_extra = gain * alpha * max(0, inv_W_mobile - threshold)
    // This is a placeholder functional form for the PA paper; not first-principles.
    parameter Real alpha(unit="1/h") = 1e-4
      "PMI coupling coefficient: fraction of excess surface-T captured on dust per hour";
    parameter Real c_W_threshold(unit="g") = 5.0
      "W surface T inventory threshold below which no extra dust capture occurs";
    parameter Real gain(unit="1") = 1.0
      "PMI gain: 0 = disabled (test baseline), 1 = enabled (default)";
    Modelica.Blocks.Interfaces.RealInput inv_W_mobile_in "Plasma W mobile inventory";
    Modelica.Blocks.Interfaces.RealOutput dust_rate_extra "Extra T capture rate on dust (g/h)";
  equation
    dust_rate_extra = gain * alpha * max(0, inv_W_mobile_in - c_W_threshold);
    annotation(uses(Modelica(version = "4.0.0")));
  end PMI;

  model VDS_3LC "Ventilation Detritiation System with explicit stack output"
    Real inventory(unit="g", start = 0, fixed = true);
    Real inflow(unit="g/h", start = 0);
    Real outflow(unit="g/h", start = 0);
    parameter Real T(unit="h") = 24;
    parameter Real Decay(unit="1/h") = 6.4e-6;
    parameter Real Epsilon(unit="1") = 1e-4;
    parameter Real Threshold(unit="g") = 0;
    Modelica.Blocks.Interfaces.RealInput from_coolant_FW;
    Modelica.Blocks.Interfaces.RealInput from_coolant_DIV;
    Modelica.Blocks.Interfaces.RealInput from_FS;
    Modelica.Blocks.Interfaces.RealInput from_Pump;
    Modelica.Blocks.Interfaces.RealInput from_TEP;
    Modelica.Blocks.Interfaces.RealInput from_TES_gas;
    Modelica.Blocks.Interfaces.RealInput from_CPS_PFC;
    Modelica.Blocks.Interfaces.RealInput from_TES;
    Modelica.Blocks.Interfaces.RealInput from_ISS;
    Modelica.Blocks.Interfaces.RealInput from_SDS;
    Modelica.Blocks.Interfaces.RealInput from_OISS;
    Modelica.Blocks.Interfaces.RealInput from_WDS;
    Modelica.Blocks.Interfaces.RealInput from_sCO2;
    Modelica.Blocks.Interfaces.RealInput from_CPS_BZ;
    Modelica.Blocks.Interfaces.RealInput from_Dust
      "Routine dust resuspension + maintenance gas-phase release captured by VDS";
    Modelica.Blocks.Interfaces.RealOutput to_WDS;
    Modelica.Blocks.Interfaces.RealOutput to_Stack;
    // [v3.0 T3.1] HT/HTO species decomposition (algebraic; T3.2 adds oxidation ODE)
    Real inv_HT (unit="g", start = 0) "HT species inventory";
    Real inv_HTO (unit="g", start = 0) "HTO species inventory";
    Real decay_rate(unit="g/h") "Tritium decay loss rate for auditor";
  equation
        inflow = from_coolant_FW + from_coolant_DIV + from_FS + from_Pump + from_TEP
          + from_TES_gas + from_CPS_PFC + from_TES + from_ISS + from_SDS + from_OISS + from_WDS
           + from_sCO2 + from_CPS_BZ + from_Dust;
    if inventory > Threshold then
      der(inventory) = inflow - (1 + Epsilon)*((inventory - Threshold)/T) - inventory*Decay;
      outflow = (inventory - Threshold)/T;
    else
      der(inventory) = inflow - Epsilon*(inventory/T) - inventory*Decay;
      outflow = 0;
    end if;
    to_WDS = outflow;
  to_Stack = if inventory > Threshold then Epsilon*outflow else Epsilon*(inventory/T);
    // [v3.0 T3.1] species split (no oxidation → all HT)
    inv_HT = inventory;
    inv_HTO = 0;
    decay_rate = inventory * Decay;
    annotation(uses(Modelica(version = "4.0.0")));
  end VDS_3LC;

  model Cycle_3LC "Cycle with 3-Level Containment Architecture"
    // [v5.1 Strategy A] D pre-loading parameters: per v5.md §7.1
    // T_steady_* taken from W0 baseline degen_res.mat last values
    // D_sub_* fraction of inventory substituted by D at startup; UQ samples 0..D_sub_*
    parameter Real T_steady_TEP(unit="g") = 1268 "TEP ZrCo bed steady inventory";
    parameter Real T_steady_I_ISS(unit="g") = 869 "I-ISS cryogenic distillation steady inventory";
    parameter Real T_steady_CPS(unit="g") = 793 "CPS_BZ steady inventory";
    parameter Real T_steady_PS(unit="g") = 685 "PS steady inventory";
    parameter Real T_steady_O_ISS(unit="g") = 483 "O-ISS steady inventory";
    parameter Real T_steady_BZFS(unit="g") = 600 "BZ + FS steady inventory (applied to BZ)";
    parameter Real D_sub_TEP(unit="1") = 1 "ZrCo bed D substitution fraction";
    parameter Real D_sub_I_ISS(unit="1") = 1 "Distillation tower D substitution fraction";
    parameter Real D_sub_CPS(unit="1") = 1 "CPS_BZ D substitution fraction";
    parameter Real D_sub_PS(unit="1") = 1 "PS D substitution fraction";
    parameter Real D_sub_O_ISS(unit="1") = 1 "O-ISS D substitution fraction";
    parameter Real D_sub_BZFS(unit="1") = 1 "BZ D substitution fraction";
    // [v5.1 M.3 Strategy D] P_fus parameterization for PPRU power scan (500/1000/1500/2000/2500/2870 MW)
    // Pulse amplitude = P_fus * 6.3935e-3 g/h (T consumption coefficient at 100% burn-up @1.5 GW reference)
    parameter Real P_fus(unit="MW") = 2870 "Fusion power; Pulse amplitude = P_fus * 6.3935e-3 g/h";
    // [v5.1 M.4 Strategy E] DD-phase transient switching (locked routing: direct→Plasma.from_FS inflow, breed→BZ.to_TES outflow)
    parameter Real t_DD_end(unit="h") = 2160 "End time of DD phase (3 months); set 0 to disable";
    parameter Real P_DD(unit="MW") = 10 "DD-phase fusion power";
    parameter Real k_DD_direct(unit="g/(h.MW)") = 0.01542 "DD direct T production coefficient (v5.1 corrected; was 5.3e-3)";
    parameter Real TBR_DD(unit="1") = 0.4 "Effective TBR during DD phase";
    // [v5.1 M.5 Strategy D] TBR_net parameterization for Monte Carlo (Uniform [1.02, 1.12])
    parameter Real TBR_net(unit="1") = 1.1 "BZ effective net Tritium Breeding Ratio (= Baseline.TBR by default); UQ range [1.02, 1.12]";
    // [v5.1 M.6 Strategy E] Residence time parameters per v5.md §7.6 (TEP/I-ISS/BZ only; CPS/PS unchanged)
    parameter Real T_TEP(unit="h") = 2 "TEP residence time; UQ range [1, 2]";
    parameter Real T_I_ISS(unit="h") = 6 "I-ISS residence time; UQ range [3, 6]";
    parameter Real T_BZ(unit="h") = 24 "BZ residence time; UQ range [8, 24]";
    // Original 18 components (VDS replaced by VDS_3LC; TES_gas instantiated for completeness)
    // [v5.1 M.1] 6 components use inventory(start=..., fixed=true) to enforce D pre-loading
    PS ps(inventory(start = T_steady_PS * (1 - D_sub_PS), fixed = true));
    TEP tep(inventory(start = T_steady_TEP * (1 - D_sub_TEP), fixed = true), T = T_TEP);
    I_ISS i_iss(T = T_I_ISS);
    DIV div;
    FW fw;
    Coolant_FW coolant_FW;
    Coolant_DIV coolant_DIV;
    CPS_PFC cps_pfc;
    O_ISS o_iss;
    BZ bz(inventory(start = T_steady_BZFS * (1 - D_sub_BZFS), fixed = true), t_DD_end = t_DD_end, P_DD = P_DD, k_DD_direct = k_DD_direct, TBR_DD = TBR_DD, TBR = TBR_net, T = T_BZ);
    TES tes;
    TES_gas tes_gas;
    Coolant_S_CO2 coolant_S_CO2;
    CPS_BZ cps_bz(inventory(start = T_steady_CPS * (1 - D_sub_CPS), fixed = true));
    WDS wds;
    Plasma plasma(t_DD_end = t_DD_end, P_DD = P_DD, k_DD_direct = k_DD_direct);
    FS fs;
    SDS sds;
    Pulse pulse(power = P_fus);
    VDS_3LC vds;
    // New 3LC nodes
    Secondary_Containment sc;
    Tertiary_Containment tc;
    Stack_Release stack;
    HX_Permeation hx_perm;
    HX_Permeation_Water hx_perm_water "DIV pressurized-water loop HX permeation to secondary steam side";
    Solid_Waste solid_waste;
    Liquid_Release liquid_release "WDS detritiated water effluent release monitor";
    Dust_Inventory dust "In-vessel W dust-borne tritium (safety source-term node)";
    // [v3.0 T4.3] PMI feedback: plasma W surface → dust T capture enhancement
    PMI pmi "Plasma-Material Interaction feedback node";
    // [v3.0 T3.3] Dose Estimator (single-direction sink — no feedback to release models)
    Dose_Estimator dose_est "Public dose estimation from gaseous + liquid releases";
    // [v4.0] Accident trigger signal generators (pure time-dependent, no state coupling)
    parameter Real t_LOCA(unit="h") = 1e10 "W7 LOCA trigger time";
    parameter Real dt_LOCA(unit="h") = 1.0 "W7 LOCA duration window";
    parameter Real t_LOFA(unit="h") = 1e10 "W8 LOFA trigger time";
    parameter Real dt_LOFA(unit="h") = 4.0 "W8 LOFA duration";
    parameter Real t_LOVA(unit="h") = 1e10 "W9 LOVA trigger time";
    parameter Real dt_LOVA(unit="h") = 0.5 "W9 LOVA duration";
    AccidentTrigger loca(t_trigger = t_LOCA, dt_window = dt_LOCA);
    AccidentTrigger lofa(t_trigger = t_LOFA, dt_window = dt_LOFA);
    AccidentTrigger lova(t_trigger = t_LOVA, dt_window = dt_LOVA);
  equation
    // --- Baseline main-loop connects (preserved from Cycle) ---
    connect(fw.to_coolant, coolant_FW.from_FW);
    connect(div.to_coolant, coolant_DIV.from_DIV);
    connect(coolant_DIV.to_CPS_PFC, cps_pfc.from_coolant_DIV);
    connect(coolant_FW.to_CPS_PFC, cps_pfc.from_coolant_FW);
    connect(cps_pfc.to_OISS, o_iss.from_CPS_PFC);
    connect(cps_bz.to_OISS, o_iss.from_CPS_BZ);
    connect(coolant_S_CO2.to_CPS_BZ, cps_bz.from_coolant);
    connect(bz.to_coolant, coolant_S_CO2.from_BZ);
    connect(tes.to_O_ISS, o_iss.from_TES);
    connect(coolant_FW.to_WDS, wds.from_coolant_FW);
    connect(coolant_DIV.to_WDS, wds.from_coolant_DIV);
    connect(wds.to_OISS, o_iss.from_WDS);
    connect(tep.to_ISS, i_iss.from_TEP);
    connect(ps.to_tep, tep.from_pump);
    connect(plasma.to_DIV, div.from_plasma);
    connect(plasma.to_FW, fw.from_plasma);
    connect(plasma.to_PS, ps.from_plasma);
    connect(plasma.from_FS, fs.to_plasma);
    connect(plasma.fueling_demand_out, fs.demand_from_plasma);
    connect(o_iss.to_SDS, sds.from_OISS);
    connect(i_iss.to_SDS, sds.from_ISS);
    connect(tep.to_SDS, sds.from_TEP);
    connect(sds.to_FS, fs.from_SDS);
    connect(pulse.y1, plasma.pulse);
    connect(pulse.y2, bz.pulse);
    connect(i_iss.to_WDS, wds.from_ISS);
    connect(ps.to_VDS, vds.from_Pump);
    connect(tep.to_VDS, vds.from_TEP);
    connect(tes_gas.to_VDS, vds.from_TES_gas);
    connect(i_iss.to_VDS, vds.from_ISS);
    connect(cps_pfc.to_VDS, vds.from_CPS_PFC);
    connect(sds.to_VDS, vds.from_SDS);
    connect(coolant_DIV.to_VDS, vds.from_coolant_DIV);
    connect(fs.to_VDS, vds.from_FS);
    connect(coolant_FW.to_VDS, vds.from_coolant_FW);
    connect(o_iss.to_VDS, vds.from_OISS);
    connect(cps_bz.to_VDS, vds.from_CPS_BZ);
    connect(wds.to_VDS, vds.from_WDS);
    connect(tes.to_VDS, vds.from_TES);
    connect(coolant_S_CO2.to_VDS, vds.from_sCO2);
    connect(vds.to_WDS, wds.from_VDS);
    connect(bz.to_TES, tes_gas.from_BZ);
    connect(tes_gas.to_TES, tes.from_TES_gas);
    connect(fw.to_Secondary, sc.from_FW);
    connect(div.to_Secondary, sc.from_DIV);
    // --- NEW: 16 to_Secondary -> sc.from_* ---
    connect(ps.to_Secondary, sc.from_PS);
    connect(tep.to_Secondary, sc.from_TEP);
    connect(tes_gas.to_Secondary, sc.from_TES_gas);
    connect(tes.to_Secondary, sc.from_TES);
    connect(o_iss.to_Secondary, sc.from_O_ISS);
    connect(wds.to_Secondary, sc.from_WDS);
    connect(coolant_FW.to_Secondary, sc.from_Coolant_FW);
    connect(coolant_DIV.to_Secondary, sc.from_Coolant_DIV);
    connect(cps_pfc.to_Secondary, sc.from_CPS_PFC);
    connect(coolant_S_CO2.to_Secondary, sc.from_Coolant_sCO2);
    connect(cps_bz.to_Secondary, sc.from_CPS_BZ);
    connect(i_iss.to_Secondary, sc.from_I_ISS);
    connect(fs.to_Secondary, sc.from_FS);
    connect(sds.to_Secondary, sc.from_SDS);
    // --- NEW: SC -> Tertiary & WDS backflow ---
    connect(sc.to_Tertiary, tc.from_Secondary);
    connect(sc.to_WDS, wds.from_SC);
    // --- NEW: TC -> WDS & Stack ---
    connect(tc.to_WDS, wds.from_TC);
    connect(tc.to_Stack, stack.from_Tertiary);
    // --- VDS exhaust → TC (HVAC) per 3-level containment principle ---
    connect(vds.to_Stack, tc.from_VDS);
    // --- NEW: HX_Permeation -> Stack ---
    connect(hx_perm.to_Stack, stack.from_HX);
    // --- NEW: Solid_Waste -> Tertiary ---
    connect(solid_waste.to_Tertiary, tc.from_Maintenance);
    // --- TES_gas: now active in BZ → TES_gas → TES chain ---
    // from_BZ connected above; from_TES is feedback from liquid TES recirculation (set 0 unless recirculation loop exists)
    // --- [v4.0] Accident trigger signal distribution (pure connect, no equations) ---
    connect(loca.trigger, coolant_FW.loca_trigger);
    connect(loca.trigger, coolant_DIV.loca_trigger);
    connect(loca.trigger, dust.loca_trigger);
    connect(lofa.trigger, fw.lofa_trigger);
    connect(lofa.trigger, div.lofa_trigger);
    connect(lova.trigger, fw.lova_trigger);
    connect(lova.trigger, div.lova_trigger);
    // --- cross-instance algebraic couplings ---
    connect(fw.to_solid_waste, solid_waste.from_FW_outflow);
    connect(div.to_solid_waste, solid_waste.from_DIV_outflow);
    connect(bz.to_solid_waste, solid_waste.from_BZ_outflow);
    connect(coolant_S_CO2.inventory_out, hx_perm.coolant_inventory);
    connect(coolant_DIV.inventory_out, hx_perm_water.coolant_inventory);
    connect(hx_perm.permeation_flux_out, coolant_S_CO2.hx_loss);
    connect(hx_perm_water.permeation_flux_out, coolant_DIV.hx_loss);
    // --- NEW: HX_Permeation_Water -> Stack ---
    connect(hx_perm_water.to_Stack, stack.from_HX_water);
    // --- NEW: WDS liquid effluent -> Liquid_Release ---
    connect(wds.to_Liquid_Release, liquid_release.from_WDS);
    // --- NEW: Dose_Estimator (single-direction sink, T3.3) ---
    connect(stack.cumulative_release_out, dose_est.stack_cumulative);
    connect(liquid_release.cumulative_release_out, dose_est.liquid_cumulative);
    // --- NEW: Dust_Inventory (Tier-2.5 safety source-term node) ---
    connect(fw.to_dust, dust.from_FW_outflow);
    connect(div.to_dust, dust.from_DIV_outflow);
    connect(plasma.inv_W_mobile_out, pmi.inv_W_mobile_in);
    connect(pmi.dust_rate_extra, dust.from_PMI);
    connect(dust.to_VDS,          vds.from_Dust);
    connect(dust.to_Solid_Waste,  solid_waste.from_Dust);
    connect(dust.to_Secondary,    sc.from_Dust);
    annotation(uses(Modelica(version = "4.0.0")));
  end Cycle_3LC;
  annotation(
    Icon,
    uses(Modelica(version = "4.0.0")));
end CFEDR_3LC;
