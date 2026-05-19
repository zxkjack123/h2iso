"""Single column solve example.

Demonstrates solving the Wang 2022 ISS-I CD2 column (75 stages)
for D₂/DT separation using the h2iso MESH solver with continuation.

Usage:
    python docs/examples/single_column.py
"""

from __future__ import annotations

import numpy as np

from h2iso.mesh import ColumnSpec, ContinuationSolver
from h2iso.mesh.export import export_csv


def main():
    # Define feed: 98% D2, 2% DT
    feed = np.zeros(6)
    feed[3] = 0.98  # D2
    feed[4] = 0.02  # DT

    # Column specification (start at 15 stages for warm-start)
    spec = ColumnSpec(
        n_stages=15,
        feed_stage=8,
        feed_flow=80.357,  # mol/h
        feed_composition=feed,
        pressure=90_000,  # Pa
        reflux_ratio=15.0,
        distillate_to_feed=0.979,
    )

    # Continuation: 15 → 30 → 75 stages
    solver = ContinuationSolver()
    solver.add_step("N", target=30, n_substeps=1)
    solver.add_step("N", target=75, n_substeps=3)

    print("Solving CD2 75-stage column...")
    result = solver.solve(spec)
    col = result.final

    # Print summary
    print(f"\nConvergence: {col.convergence_info['status']}")
    print(f"Top D2 purity:  {col.x_profile[0, 3]:.4%}")
    print(f"Top DT:         {col.x_profile[0, 4]:.6%}")
    print(f"Bottom DT:      {col.x_profile[-1, 4]:.4%}")
    print(f"T_top:          {col.T_profile[0]:.2f} K")
    print(f"T_bottom:       {col.T_profile[-1]:.2f} K")
    print(f"Condenser duty: {col.condenser_duty:.1f} W")
    print(f"Reboiler duty:  {col.reboiler_duty:.1f} W")

    # Export profiles
    export_csv(col, "cd2_profiles.csv")
    print("\nProfiles exported to cd2_profiles.csv")


if __name__ == "__main__":
    main()
