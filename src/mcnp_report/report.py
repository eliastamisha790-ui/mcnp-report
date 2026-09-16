from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

try:
    import xlsxwriter
except ImportError as exc:  # pragma: no cover - packaging/runtime guard
    raise RuntimeError("缺少 XlsxWriter，请先安装项目依赖。") from exc

from .errors import WorkbookError
from .models import AIResult, ParseResult


EXCEL_MAX_ROWS = 1_048_576
TALLY_ROWS_PER_SHEET = EXCEL_MAX_ROWS - 3
BLUE = "#17365D"
MID_BLUE = "#4472C4"
LIGHT_BLUE = "#D9EAF7"
PALE_BLUE = "#EAF2F8"
AMBER = "#FFF2CC"
RED = "#FCE4D6"
GREEN = "#E2F0D9"
GRAY = "#E7E6E6"
TEXT = "#222222"


def _formats(workbook: xlsxwriter.Workbook) -> dict[str, Any]:
    base = {"font_name": "Arial", "font_size": 10, "font_color": TEXT, "valign": "vcenter"}
    return {
        "title": workbook.add_format({**base, "font_size": 15, "bold": True, "font_color": BLUE, "bottom": 2, "bottom_color": MID_BLUE}),
        "subtitle": workbook.add_format({**base, "italic": True, "font_color": "#666666"}),
        "section": workbook.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": BLUE, "top": 1, "bottom": 1}),
        "header": workbook.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": MID_BLUE, "align": "center", "border": 1, "border_color": "#FFFFFF", "text_wrap": True}),
        "label": workbook.add_format({**base, "bold": True, "bg_color": PALE_BLUE, "bottom": 1, "bottom_color": "#D9E2F3"}),
        "text": workbook.add_format(base),
        "wrap": workbook.add_format({**base, "text_wrap": True, "valign": "top"}),
        "integer": workbook.add_format({**base, "num_format": "#,##0"}),
        "number": workbook.add_format({**base, "num_format": "0.00000E+00"}),
        "decimal": workbook.add_format({**base, "num_format": "0.0000"}),
        "percent": workbook.add_format({**base, "num_format": "0.00%"}),
        "good": workbook.add_format({**base, "bold": True, "font_color": "#375623", "bg_color": GREEN}),
        "warn": workbook.add_format({**base, "bold": True, "font_color": "#9C5700", "bg_color": AMBER}),
        "bad": workbook.add_format({**base, "bold": True, "font_color": "#9C0006", "bg_color": RED}),
        "mono": workbook.add_format({**base, "font_name": "Consolas", "font_size": 9}),
        "small": workbook.add_format({**base, "font_size": 9, "font_color": "#666666"}),
    }


def _setup_sheet(sheet: Any, tab_color: str | None = None, landscape: bool = True) -> None:
    sheet.hide_gridlines(2)
    if tab_color:
        sheet.set_tab_color(tab_color)
    sheet.set_landscape() if landscape else sheet.set_portrait()
    sheet.set_margins(0.35, 0.35, 0.5, 0.5)
    sheet.set_header("&LMCNP 输出分析报告&R&F")
    sheet.set_footer("&L仅支持 MCNP6, 1.0 固定源输出&C第 &P / &N 页&R由 mcnp-report 生成")


def _title(sheet: Any, fmt: dict[str, Any], text: str, last_col: int) -> None:
    sheet.set_row(0, 8)
    sheet.set_row(1, 23)
    sheet.write(1, 0, text, fmt["title"])
    sheet.set_row(2, 7)


def _section_row(sheet: Any, row: int, label: str, last_col: int, style: Any) -> None:
    sheet.write(row, 0, label, style)
    for col in range(1, last_col + 1):
        sheet.write_blank(row, col, None, style)


def _zh_token(value: str) -> str:
    mapping = {
        "yes": "是", "no": "否", "random": "随机", "constant": "恒定",
        "increase": "增加", "decrease": "下降",
    }
    return mapping.get(value.lower(), value)


def _write_value(sheet: Any, row: int, col: int, value: Any, fmt: Any) -> None:
    if value is None:
        sheet.write_blank(row, col, None, fmt)
    elif isinstance(value, bool):
        sheet.write(row, col, "是" if value else "否", fmt)
    elif isinstance(value, (int, float)):
        sheet.write_number(row, col, value, fmt)
    else:
        sheet.write(row, col, str(value), fmt)


def _overview(workbook: Any, sheet: Any, result: ParseResult, ai: AIResult, fmt: dict[str, Any], stats_sheet: str) -> None:
    _setup_sheet(sheet, BLUE)
    _title(sheet, fmt, "MCNP 固定源计算结果", 9)
    metadata = result.metadata
    tally = result.tally_summaries[0] if result.tally_summaries else None
    final_tfc = result.tfc_points[-1] if result.tfc_points else None

    sheet.set_column("A:A", 23); sheet.set_column("B:B", 22)
    sheet.set_column("C:C", 3); sheet.set_column("D:J", 13)
    _section_row(sheet, 3, "运行概要", 1, fmt["section"])
    rows = [
        ("输出文件", Path(metadata.source_path).name, "text"),
        ("MCNP 版本", f"{metadata.code_name}, {metadata.code_version}", "text"),
        ("历史数 NPS", metadata.nps, "integer"),
        ("计算时间 (min)", metadata.computer_time_minutes, "decimal"),
        ("终止状态", "正常终止" if metadata.normal_termination else "未确认正常终止", "good" if metadata.normal_termination else "bad"),
        ("F4 总值", tally.total if tally else None, "number"),
        ("F4 相对误差", tally.relative_error if tally else None, "decimal"),
        ("最终 FOM", final_tfc.fom if final_tfc else None, "integer"),
        ("警告数", metadata.warning_count, "integer"),
        ("未通过统计检查", tally.missed_checks if tally else None, "integer"),
    ]
    for idx, (label, value, style) in enumerate(rows, 4):
        sheet.write(idx, 0, label, fmt["label"])
        _write_value(sheet, idx, 1, value, fmt[style])

    _section_row(sheet, 15, "中文结论", 1, fmt["section"])
    sheet.set_row(16, 54)
    sheet.write("A17", "结论", fmt["label"]); sheet.write("B17", ai.overview, fmt["wrap"])
    sheet.set_column("B:B", 44)
    row = 18
    for finding in ai.findings:
        sheet.set_row(row, 44)
        severity = {"critical": "严重", "warning": "警告", "info": "提示"}.get(finding.severity, finding.severity)
        sheet.write(row, 0, f"{severity}：{finding.title}", fmt["bad"] if finding.severity == "critical" else fmt["warn"] if finding.severity == "warning" else fmt["label"])
        sheet.write(row, 1, finding.interpretation + (f"  [事实: {', '.join(finding.fact_ids)}]" if finding.fact_ids else ""), fmt["wrap"])
        row += 1
    sheet.write(row, 0, "解读来源", fmt["label"])
    sheet.write(row, 1, f"{ai.provider} / {ai.status}" + (f"  降级原因：{ai.error}" if ai.error else ""), fmt["wrap"])

    if result.tfc_points:
        first = 4 + len(result.statistical_checks) + 3
        last = first + len(result.tfc_points) - 1
        mean_chart = workbook.add_chart({"type": "line"})
        mean_chart.add_series({
            "name": "Tally 均值", "categories": f"='{stats_sheet}'!$B${first + 1}:$B${last + 1}",
            "values": f"='{stats_sheet}'!$C${first + 1}:$C${last + 1}",
            "line": {"color": MID_BLUE, "width": 2.0},
        })
        mean_chart.set_title({"name": "TFC 均值收敛"}); mean_chart.set_x_axis({"name": "NPS", "num_format": "0.0E+00"})
        mean_chart.set_y_axis({"name": "Tally 均值", "num_format": "0.00E+00", "major_gridlines": {"visible": True, "line": {"color": "#D9E2F3"}}})
        mean_chart.set_legend({"none": True}); mean_chart.set_style(10)
        sheet.insert_chart("D4", mean_chart, {"x_scale": 1.22, "y_scale": 1.02})

        fom_chart = workbook.add_chart({"type": "line"})
        fom_chart.add_series({
            "name": "FOM", "categories": f"='{stats_sheet}'!$B${first + 1}:$B${last + 1}",
            "values": f"='{stats_sheet}'!$G${first + 1}:$G${last + 1}",
            "line": {"color": "#70AD47", "width": 2.0},
        })
        fom_chart.set_title({"name": "TFC 品质因子 FOM"}); fom_chart.set_x_axis({"name": "NPS", "num_format": "0.0E+00"})
        fom_chart.set_y_axis({"name": "FOM", "num_format": "0.00E+00", "min": 0, "major_gridlines": {"visible": True, "line": {"color": "#E2F0D9"}}})
        fom_chart.set_legend({"none": True}); fom_chart.set_style(10)
        sheet.insert_chart("D20", fom_chart, {"x_scale": 1.22, "y_scale": 1.02})
    sheet.print_area(0, 0, max(row + 1, 35), 9)


def _tally_sheets(workbook: Any, result: ParseResult, fmt: dict[str, Any]) -> list[str]:
    count = result.store.tally_count()
    sheet_count = max(1, (count + TALLY_ROWS_PER_SHEET - 1) // TALLY_ROWS_PER_SHEET)
    sheets = []
    iterator = iter(result.store.iter_tally_bins())
    summaries = {item.tally_id: item for item in result.tally_summaries}
    headers = ["序号", "Tally", "类型", "粒子", "Cell", "体积 (cm³)", "能量上限 (MeV)", "结果", "结果单位", "相对误差", "行类型", "质量标记", "源行号"]
    widths = [11, 9, 9, 13, 10, 15, 18, 17, 14, 14, 12, 12, 12]
    for idx in range(sheet_count):
        name = "Tally结果" if sheet_count == 1 else f"Tally结果_{idx + 1:02d}"
        sheet = workbook.add_worksheet(name); sheets.append(name)
        _setup_sheet(sheet, MID_BLUE); _title(sheet, fmt, f"Tally 分箱结果（第 {idx + 1}/{sheet_count} 表）", len(headers) - 1)
        sheet.write_row(3, 0, headers, fmt["header"]); sheet.freeze_panes(4, 5); sheet.autofilter(3, 0, 3, len(headers) - 1)
        for col, width in enumerate(widths): sheet.set_column(col, col, width)
        written = 0
        while written < TALLY_ROWS_PER_SHEET:
            try: item = next(iterator)
            except StopIteration: break
            row = 4 + written
            summary = summaries.get(item.tally_id)
            particle = "光子 (photon)" if item.particles.lower() in {"photon", "photons"} else item.particles
            row_kind = "能量分箱" if item.row_kind == "energy_bin" else "总计" if item.row_kind == "total" else item.row_kind
            values = [item.seq, item.tally_id, item.tally_type, particle, item.cell, item.volume, item.energy_upper_mev, item.result, summary.units if summary else "", item.relative_error, row_kind, item.quality_flag, item.source_line]
            for col, value in enumerate(values):
                style = fmt["number"] if col in {5, 6, 7} else fmt["decimal"] if col == 9 else fmt["integer"] if col in {0, 1, 2, 12} else fmt["text"]
                _write_value(sheet, row, col, value, style)
            written += 1
        if written:
            end = 3 + written
            sheet.autofilter(3, 0, end, len(headers) - 1)
            sheet.conditional_format(4, 9, end, 9, {"type": "cell", "criteria": ">", "value": 0.10, "format": fmt["bad"]})
            sheet.conditional_format(4, 11, end, 11, {"type": "text", "criteria": "containing", "value": "零值", "format": fmt["warn"]})
        sheet.repeat_rows(3); sheet.fit_to_pages(1, 0)
    return sheets


def _statistics(sheet: Any, result: ParseResult, fmt: dict[str, Any]) -> None:
    _setup_sheet(sheet, "#70AD47"); _title(sheet, fmt, "Tally 统计诊断", 7)
    widths = [11, 42, 42, 32, 18, 18, 13, 13]
    for col, width in enumerate(widths): sheet.set_column(col, col, width)
    sheet.write_row(3, 0, ["Tally", "检查序号", "检查项", "MCNP 原始项", "期望", "观测", "通过", "源行号"], fmt["header"])
    row = 4
    for item in result.statistical_checks:
        values = [item.tally_id, item.check_no, item.name_zh, item.name_en, _zh_token(item.desired), _zh_token(item.observed), "是" if item.passed else "否", item.source_line]
        for col, value in enumerate(values): _write_value(sheet, row, col, value, fmt["integer"] if col in {0, 1, 7} else fmt["text"])
        row += 1
    if row > 4:
        sheet.conditional_format(4, 6, row - 1, 6, {"type": "text", "criteria": "containing", "value": "否", "format": fmt["bad"]})

    row += 1
    _section_row(sheet, row, "TFC 序列", 7, fmt["section"])
    row += 1
    sheet.write_row(row, 0, ["Tally", "NPS", "均值", "相对误差", "VOV", "PDF 斜率", "FOM", "源行号"], fmt["header"])
    row += 1
    for item in result.tfc_points:
        values = [item.tally_id, item.nps, item.mean, item.error, item.vov, item.slope, item.fom, item.source_line]
        for col, value in enumerate(values):
            style = fmt["integer"] if col in {0, 1, 7} else fmt["number"] if col in {2, 4} else fmt["decimal"] if col in {3, 5} else fmt["integer"]
            _write_value(sheet, row, col, value, style)
        row += 1

    row += 1; _section_row(sheet, row, "PRINT 160 指标", 7, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["Tally", "指标", "专业中文", "数值", "源行号"], fmt["header"]); row += 1
    for item in result.table160_metrics:
        sheet.write_number(row, 0, item.tally_id, fmt["integer"]); sheet.write(row, 1, item.name_en, fmt["text"])
        sheet.write(row, 2, item.name_zh, fmt["text"]); sheet.write_number(row, 3, item.value, fmt["number"]); sheet.write_number(row, 4, item.source_line, fmt["integer"]); row += 1

    row += 1; _section_row(sheet, row, "PRINT 161 未归一化 tally 密度", 7, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["Tally", "横坐标", "Tally 数", "数密度", "对数密度", "行类型", "源行号"], fmt["header"]); row += 1
    for item in result.store.iter_density_bins():
        values = [item.tally_id, item.abscissa, item.tally_number, item.num_density, item.log_density, "分箱" if item.row_kind == "bin" else "总计", item.source_line]
        for col, value in enumerate(values):
            style = fmt["integer"] if col in {0, 2, 6} else fmt["number"] if col in {1, 3, 4} else fmt["text"]
            _write_value(sheet, row, col, value, style)
        row += 1
    sheet.freeze_panes(4, 2); sheet.repeat_rows(3)


def _particles(sheet: Any, result: ParseResult, fmt: dict[str, Any]) -> None:
    _setup_sheet(sheet, "#5B9BD5"); _title(sheet, fmt, "粒子与单元", 10)
    sheet.set_column("A:A", 12); sheet.set_column("B:K", 16)
    row = 3
    _section_row(sheet, row, "PRINT 60 单元参数", 8, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["Cell", "材料", "原子密度", "质量密度", "体积", "质量", "块数", "光子重要性", "源行号"], fmt["header"]); row += 1
    for item in result.cells:
        values = [item.cell, item.material, item.atom_density, item.gram_density, item.volume, item.mass, item.pieces, item.importance, item.source_line]
        for col, value in enumerate(values): _write_value(sheet, row, col, value, fmt["integer"] if col in {0, 1, 6, 8} else fmt["number"])
        row += 1
    row += 1; _section_row(sheet, row, "PRINT 101 粒子能量限制 (MeV)", 9, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["ID", "缩写", "粒子", "截断能量", "最大能量", "最小表上限", "最大表上限", "低于此值始终用表", "高于此值始终用模型", "源行号"], fmt["header"]); row += 1
    for item in result.particle_limits:
        values = list(asdict(item).values())
        for col, value in enumerate(values): _write_value(sheet, row, col, value, fmt["integer"] if col in {0, 9} else fmt["number"] if col >= 3 else fmt["text"])
        row += 1
    row += 1; _section_row(sheet, row, "PRINT 126 单元活性", 9, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["Cell", "进入径迹", "粒子数", "碰撞数", "碰撞权重/历史", "数加权能量", "通量加权能量", "平均径迹权重", "平均自由程 (cm)", "源行号"], fmt["header"]); row += 1
    for item in result.cell_activity:
        values = list(asdict(item).values())
        for col, value in enumerate(values): _write_value(sheet, row, col, value, fmt["integer"] if col in {0, 1, 2, 3, 9} else fmt["number"])
        row += 1
    row += 1; _section_row(sheet, row, "Problem Summary 粒子产生与损失", 6, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["粒子", "类别", "过程", "径迹", "权重", "能量", "源行号"], fmt["header"]); row += 1
    for item in result.balances:
        process_zh = {
            "source": "源粒子", "escape": "逃逸", "nucl. interaction": "核相互作用", "energy cutoff": "能量截断",
            "particle decay": "粒子衰变", "time cutoff": "时间截断", "weight window": "权重窗", "cell importance": "单元重要性",
            "weight cutoff": "权重截断", "e or t importance": "能量/时间重要性", "dxtran": "DXTRAN", "forced collisions": "强制碰撞",
            "exp. transform": "指数变换", "from neutrons": "来自中子", "compton scatter": "康普顿散射", "bremsstrahlung": "韧致辐射",
            "capture": "俘获", "pair production": "电子对产生", "photonuclear": "光核反应", "photonuclear abs": "光核吸收",
            "electron x-rays": "电子 X 射线", "loss to photofis": "光致裂变损失", "compton fluores": "康普顿荧光", "total": "总计",
        }.get(item.process, item.process)
        values = ["光子 (photon)", "产生" if item.side == "creation" else "损失", process_zh, item.tracks, item.weight, item.energy, item.source_line]
        for col, value in enumerate(values): _write_value(sheet, row, col, value, fmt["integer"] if col in {3, 6} else fmt["number"] if col in {4, 5} else fmt["text"])
        row += 1
    sheet.freeze_panes(5, 2)


def _nuclear(sheet: Any, result: ParseResult, fmt: dict[str, Any]) -> None:
    _setup_sheet(sheet, "#8064A2"); _title(sheet, fmt, "核数据库", 5)
    sheet.set_column("A:A", 18); sheet.set_column("B:B", 12); sheet.set_column("C:C", 26); sheet.set_column("D:D", 75); sheet.set_column("E:E", 12)
    sheet.write("A4", "XSDIR", fmt["label"]); sheet.write("B4", result.xsdir, fmt["mono"])
    sheet.write_row(5, 0, ["截面表", "长度", "库文件", "描述 / 日期", "源行号"], fmt["header"])
    row = 6
    for item in result.cross_sections:
        sheet.write(row, 0, item.table, fmt["mono"]); sheet.write_number(row, 1, item.length, fmt["integer"])
        sheet.write(row, 2, item.source_file, fmt["mono"]); sheet.write(row, 3, item.description, fmt["wrap"]); sheet.write_number(row, 4, item.source_line, fmt["integer"]); row += 1
    sheet.freeze_panes(6, 1); sheet.autofilter(5, 0, max(5, row - 1), 4)


def _inputs(sheet: Any, result: ParseResult, fmt: dict[str, Any]) -> None:
    _setup_sheet(sheet, "#A5A5A5"); _title(sheet, fmt, "MCNP 输入清单", 5)
    sheet.set_column("A:B", 12); sheet.set_column("C:C", 15); sheet.set_column("D:D", 60); sheet.set_column("E:E", 58); sheet.set_column("F:F", 12)
    sheet.write_row(3, 0, ["输入行号", "输出源行", "类别", "原始卡片", "专业中文说明", "区域"], fmt["header"])
    for row, item in enumerate(result.input_cards, 4):
        sheet.write_number(row, 0, item.input_line, fmt["integer"]); sheet.write_number(row, 1, item.source_line, fmt["integer"])
        category = {"comment": "注释", "cell": "单元", "surface": "曲面", "transform": "坐标变换", "mode": "输运模式", "importance": "重要性", "material": "材料", "data": "数据", "source": "源定义", "tally": "计数", "energy": "能量分箱", "nps": "运行控制", "blank": "空行"}.get(item.category, item.category)
        sheet.write(row, 2, category, fmt["text"]); sheet.write(row, 3, item.card, fmt["mono"]); sheet.write(row, 4, item.explanation_zh, fmt["wrap"])
        sheet.write(row, 5, "输入列表", fmt["text"])
    end = max(3, 3 + len(result.input_cards)); sheet.freeze_panes(4, 3); sheet.autofilter(3, 0, end, 5)


def _audit(sheet: Any, result: ParseResult, ai: AIResult, fmt: dict[str, Any]) -> None:
    _setup_sheet(sheet, "#7F7F7F"); _title(sheet, fmt, "解析审计", 7)
    sheet.set_column("A:A", 28); sheet.set_column("B:B", 20); sheet.set_column("C:C", 16); sheet.set_column("D:D", 52); sheet.set_column("E:E", 70); sheet.set_column("F:F", 68); sheet.set_column("G:H", 14)
    metadata = result.metadata
    items = [
        ("文件名", Path(metadata.source_path).name), ("SHA-256", metadata.sha256), ("文件大小 (byte)", metadata.file_size),
        ("编码", metadata.encoding), ("识别覆盖率", sum(s.record_count for s in result.sections if s.status == "recognized") / max(1, sum(s.record_count for s in result.sections))),
        ("受支持版本", "MCNP6, 1.0 固定源"), ("解析器版本", "0.2.1"),
        ("AI 状态", f"{ai.provider} / {ai.status}"),
    ]
    for row, (label, value) in enumerate(items, 3):
        style = fmt["percent"] if label == "识别覆盖率" else fmt["integer"] if isinstance(value, int) else fmt["mono"] if label == "SHA-256" else fmt["text"]
        sheet.write(row, 0, label, fmt["label"]); _write_value(sheet, row, 1, value, style)
    row = 12; _section_row(sheet, row, "段落覆盖", 5, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["段落", "状态", "起始行", "结束行", "记录行数", "段 SHA-256"], fmt["header"]); row += 1
    for item in result.sections:
        values = [item.name, item.status, item.start_line, item.end_line, item.record_count, item.sha256]
        for col, value in enumerate(values): _write_value(sheet, row, col, value, fmt["integer"] if col in {2, 3, 4} else fmt["mono"] if col == 5 else fmt["text"])
        row += 1
    row += 1; _section_row(sheet, row, "诊断与警告", 4, fmt["section"]); row += 1
    sheet.write_row(row, 0, ["严重级别", "源行号", "类别", "中文说明", "MCNP 原始消息"], fmt["header"]); row += 1
    for item in result.diagnostics:
        sheet.set_row(row, 45)
        sheet.write(row, 0, item.severity, fmt["text"]); sheet.write_number(row, 1, item.source_line, fmt["integer"])
        sheet.write(row, 2, item.category, fmt["text"]); sheet.write(row, 3, item.message_zh, fmt["wrap"]); sheet.write(row, 4, item.message_en, fmt["wrap"]); row += 1
    sheet.freeze_panes(14, 2)


def write_report(result: ParseResult, ai_result: AIResult, output_path: str | Path) -> Path:
    """Write a professional Chinese Excel workbook with typed MCNP records."""
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = None
    try:
        workbook = xlsxwriter.Workbook(str(destination), {"constant_memory": True})
        workbook.use_zip64()
        workbook.set_properties({
            "title": "MCNP 固定源输出分析报告", "subject": "MCNP6, 1.0 结果中文化与统计审计",
            "author": "mcnp-report", "comments": "规则解析结果；AI 仅用于结构化事实解读。",
        })
        fmt = _formats(workbook)
        overview = workbook.add_worksheet("总览")
        # Detail worksheets are created in the explicit user-requested order.
        tally_names = _tally_sheets(workbook, result, fmt)
        statistics = workbook.add_worksheet("统计诊断")
        particles = workbook.add_worksheet("粒子与单元")
        nuclear = workbook.add_worksheet("核数据库")
        inputs = workbook.add_worksheet("输入清单")
        audit = workbook.add_worksheet("解析审计")
        _statistics(statistics, result, fmt)
        _particles(particles, result, fmt)
        _nuclear(nuclear, result, fmt)
        _inputs(inputs, result, fmt)
        _audit(audit, result, ai_result, fmt)
        _overview(workbook, overview, result, ai_result, fmt, "统计诊断")
        overview.activate()
        workbook.close()
        return destination
    except Exception as exc:
        try:
            if workbook is not None:
                workbook.close()
            if destination.exists():
                destination.unlink()
        except OSError:
            pass
        raise WorkbookError(f"写入 Excel 失败：{exc}") from exc
