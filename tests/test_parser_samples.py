from pathlib import Path

import pytest

from mcnp_report.errors import PartialParseError, UnsupportedVersionError
from mcnp_report.parser import parse_output


SAMPLES = [
    (Path(r"D:\mcnpproject\1.out"), 0.15, 544429.0, 1),
    (Path(r"D:\mcnpproject\ceshi.out"), 1.58, 52649.0, 2),
]


@pytest.mark.parametrize("path,minutes,fom,missed", SAMPLES)
def test_real_samples(path, minutes, fom, missed):
    if not path.is_file():
        pytest.skip(f"外部样本不存在：{path}")
    result = parse_output(path, strict=True)
    try:
        tally = result.tally_summaries[0]
        assert result.metadata.code_version == "1.0"
        assert result.metadata.nps == 10_000_000
        assert result.metadata.computer_time_minutes == pytest.approx(minutes)
        assert result.metadata.warning_count == 6
        assert result.metadata.normal_termination is True
        assert tally.tally_id == 4 and tally.tally_type == 4
        assert tally.total == pytest.approx(4.95542e-4)
        assert tally.relative_error == pytest.approx(0.0035)
        assert tally.reported_bins == 2003
        assert tally.missed_checks == missed
        assert result.store.tally_count() == 2003
        assert len(result.statistical_checks) == 10
        assert len(result.tfc_points) == 20
        assert result.tfc_points[-1].fom == pytest.approx(fom)
        assert result.store.density_count() == 51
        assert len(result.cross_sections) == 10
        assert len(result.cells) == 4
        assert len(result.cell_activity) == 3
        assert not [s for s in result.sections if s.status != "recognized"]
    finally:
        result.close()


def test_rejects_wrong_version(tmp_path):
    source = tmp_path / "wrong.out"
    source.write_text("Code Name & Version = MCNP6, 6.3.1\n", encoding="ascii")
    with pytest.raises(UnsupportedVersionError):
        parse_output(source)


def test_truncated_file_strict_failure(tmp_path):
    source = tmp_path / "truncated.out"
    source.write_text(
        "Code Name & Version = MCNP6, 1.0\n"
        "1mcnp     version 6     ld=05/08/13\n"
        "         1-       mode p\n"
        "1tally        4        nps =    1000\n"
        "           tally type 4 track length estimate. units 1/cm**2\n",
        encoding="ascii",
    )
    result = parse_output(source, strict=False)
    try:
        assert any(item.category == "parser" for item in result.diagnostics)
    finally: result.close()
    with pytest.raises(PartialParseError):
        parse_output(source, strict=True)


def test_rejects_unsupported_kcode(tmp_path):
    source = tmp_path / "kcode.out"
    source.write_text(
        "Code Name & Version = MCNP6, 1.0\n"
        "1mcnp     version 6     ld=05/08/13\n"
        "         1-       mode n\n"
        "         2-       kcode 1000 1.0 30 100\n",
        encoding="ascii",
    )
    with pytest.raises(UnsupportedVersionError):
        parse_output(source)


def test_unknown_page_is_audited_and_strictly_rejected(tmp_path):
    source = tmp_path / "unknown.out"
    source.write_text(
        "Code Name & Version = MCNP6, 1.0\n"
        "1mcnp     version 6     ld=05/08/13\n"
        "         1-       mode p\n"
        "1future table not implemented\n"
        " run terminated when    1000  particle histories were done.\n",
        encoding="ascii",
    )
    result = parse_output(source)
    try:
        assert any(section.status == "unsupported" for section in result.sections)
    finally: result.close()
    with pytest.raises(PartialParseError):
        parse_output(source, strict=True)
