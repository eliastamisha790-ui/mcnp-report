from pathlib import Path

from mcnp_report.errors import UnsupportedVersionError
from mcnp_report.gui import _friendly_error, _initial_input


def test_initial_input_accepts_dragged_out_file(tmp_path):
    source = tmp_path / "中文 sample.out"
    source.write_text("synthetic", encoding="utf-8")
    assert _initial_input([str(source)]) == str(source.resolve())
    assert _initial_input(["--smoke-test"]) == ""


def test_friendly_error():
    assert "版本不支持" in _friendly_error(UnsupportedVersionError("MCNP6.3"))
