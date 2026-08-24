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
        assert abs(z[0] - 0.02135) < 0.001
        assert abs(z[4] - 0.357) < 0.01
        assert abs(z[5] - 0.2384) < 0.01
