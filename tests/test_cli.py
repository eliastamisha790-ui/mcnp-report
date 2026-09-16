from pathlib import Path

from mcnp_report.cli import main


def test_drag_drop_style_and_duplicate_name(tmp_path):
    source = Path(r"D:\mcnpproject\1.out")
    if not source.is_file(): return
    output = tmp_path / "result.xlsx"
    assert main([str(source), "--ai", "off", "-o", str(output)]) == 0
    assert output.is_file()
    assert main([str(source), "--ai", "off", "-o", str(output)]) == 2
    assert main([str(source), "--ai", "off", "-o", str(output), "--overwrite"]) == 0

