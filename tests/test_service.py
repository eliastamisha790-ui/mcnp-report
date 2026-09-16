from pathlib import Path

import openpyxl

from mcnp_report.service import AnalysisRequest, analyze_file, default_output_path


SYNTHETIC = Path(__file__).resolve().parents[1] / "training_data" / "synthetic" / "high_error_bins.out"


def test_default_output_path():
    assert default_output_path(SYNTHETIC).name == "high_error_bins_mcnp_report.xlsx"


def test_shared_gui_cli_service(tmp_path):
    output = tmp_path / "gui service 报告.xlsx"
    stages = []
    outcome = analyze_file(AnalysisRequest(str(SYNTHETIC), str(output), ai_mode="off"), lambda stage, message: stages.append(stage))
    assert stages == ["parse", "ai", "excel", "done"]
    assert outcome.output_path == output.resolve()
    assert outcome.tally_rows == 4 and outcome.tfc_points == 5
    assert outcome.ai_provider == "local-rules"
    workbook = openpyxl.load_workbook(output, data_only=True)
    assert workbook["总览"]["B10"].value == 8.2e-6
    assert workbook["总览"]["B11"].value == 0.12
    assert len(workbook["总览"]._charts) == 2
    workbook.close()
