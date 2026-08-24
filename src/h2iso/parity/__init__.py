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
