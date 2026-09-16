import json
from pathlib import Path

import pytest

from mcnp_report.errors import PartialParseError, UnsupportedVersionError
from mcnp_report.parser import parse_output


ROOT = Path(__file__).resolve().parents[1] / "training_data" / "synthetic"


@pytest.mark.parametrize("filename", ["normal_low_error.out", "high_error_bins.out", "stable_high_precision.out"])
def test_supported_synthetic_cases(filename):
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["cases"][filename]
    result = parse_output(ROOT / filename, strict=True)
    try:
        tally = result.tally_summaries[0]
        assert result.metadata.nps == expected["nps"]
        assert result.metadata.computer_time_minutes == pytest.approx(expected["minutes"])
        assert tally.total == pytest.approx(expected["total"])
        assert tally.relative_error == pytest.approx(expected["error"])
        assert tally.missed_checks == expected["missed"]
        assert result.tfc_points[-1].fom == pytest.approx(expected["fom"])
        assert result.store.tally_count() == len(expected["bins"]) + 1
        assert len(result.statistical_checks) == 10
    finally:
        result.close()


def test_synthetic_negative_cases():
    result = parse_output(ROOT / "truncated.out")
    try: assert any(item.category == "parser" for item in result.diagnostics)
    finally: result.close()
    with pytest.raises(PartialParseError): parse_output(ROOT / "truncated.out", strict=True)
    with pytest.raises(UnsupportedVersionError): parse_output(ROOT / "unsupported_version.out")
    with pytest.raises(PartialParseError): parse_output(ROOT / "unknown_table.out", strict=True)
