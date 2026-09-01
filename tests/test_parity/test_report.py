"""Test parity report generation."""

from h2iso.parity.report import generate_report, load_aspen_results


class TestReport:
    def test_aspen_only(self):
        aspen = load_aspen_results()
        report = generate_report(aspen)
        assert "ISS-I Three-Way Parity Report" in report
        assert "TC1" in report
        assert "TC5" in report
        assert "Aspen" in report

    def test_aspen_only_output_sections(self):
        aspen = load_aspen_results()
        report = generate_report(aspen)
        assert "Test Setup" in report
        assert "Summary" in report
        assert "Go/No-Go" in report
