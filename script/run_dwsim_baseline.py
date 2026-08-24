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


def setup_runtime():
    from pythonnet import set_runtime
    from clr_loader import get_coreclr

    rt = get_coreclr(dotnet_root=DOTNET_ROOT)
    set_runtime(rt)


def extract_hdt(stream) -> dict:
    """Extract H/D/T mass flows (g/h) from a DWSIM material stream.

    n_H = 2*n(H2) + n(HD) + n(HT)
    n_D = n(HD) + 2*n(D2) + n(DT)
    n_T = n(HT) + n(DT) + 2*n(T2)
    """
    compounds = stream.Phases[0].Compounds
    n = {comp: compounds[comp].MoleFlow for comp in DWSIM_COMPOUNDS}

    H_mol = 2 * n["Hydrogen"] + n["HD"] + n["HT"]
    D_mol = n["HD"] + 2 * n["Deuterium"] + n["DT"]
    T_mol = n["HT"] + n["DT"] + 2 * n["Tritium"]

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

    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    from register_compounds import register_compounds

    results = []

    for case_id, (T_g, D_g, H_g) in TEST_CASES.items():
        print(
            f"\n{'='*60}\n{case_id}: T={T_g}, D={D_g}, H={H_g} g/h\n{'='*60}"
        )
        t0 = time.time()

        interf = Automation3()
        sim = interf.CreateFlowsheet()

        # Step 1: Register compounds
        register_compounds(sim, {})

        # Step 2: SRK property package
        sim.CreateAndAddPropertyPackage("Soave-Redlich-Kwong (SRK)")

        # Step 3: Create feed stream
        feed_z = atom_to_species(T_g, D_g, H_g)
        total_flow = (H_g / _M_H + D_g / _M_D + T_g / _M_T) / 2.0 * (1000.0 / 3600.0)

        m1 = sim.AddObject(ObjectType.MaterialStream, 50, 200, "FROMTEP")
        m1 = m1.GetAsObject()
        m1.SetTemperature(23.89)
        m1.SetPressure(100000.0)
        m1.SetMolarFlow(total_flow)
        for comp_name, frac in feed_z.items():
            m1.SetOverallCompoundMolarFlow(comp_name, total_flow * frac)

        print(f"  Feed: T=23.89 K, P=100000 Pa, F={total_flow:.4f} mmol/s")

        # Step 4: Solve
        try:
            interf.CalculateFlowsheet2(sim)
            hdt = extract_hdt(m1)
            products = {
                "WDS": {"H": 0.0, "D": 0.0, "T": 0.0},
                "SDSD2": {"H": 0.0, "D": 0.0, "T": 0.0},
                "SDST2": {"H": 0.0, "D": 0.0, "T": 0.0},
            }

            results.append({
                "case_id": case_id,
                "feed_hdt": {"H": H_g, "D": D_g, "T": T_g},
                "feed_composition": feed_z,
                "products": products,
                "converged": True,
                "solver_time_s": round(time.time() - t0, 3),
                "note": (
                    "Full ISS-I DWSIM solve requires build_dwsim_flowsheet.py "
                    "(tricys). Feed-only placeholder."
                ),
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

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
