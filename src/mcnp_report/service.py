from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .ai import generate_ai
from .config import load_config, select_profile
from .errors import ConfigurationError
from .parser import parse_output
from .report import write_report


ProgressCallback = Callable[[str, str], None]


@dataclass(frozen=True)
class AnalysisRequest:
    input_path: str
    output_path: str | None = None
    ai_mode: str = "auto"
    profile: str | None = None
    config_path: str | None = None
    strict: bool = False
    overwrite: bool = False


@dataclass(frozen=True)
class AnalysisOutcome:
    output_path: Path
    tally_rows: int
    tfc_points: int
    warning_count: int
    ai_provider: str
    ai_status: str
    ai_error: str
    nps: int | None
    tally_total: float | None
    relative_error: float | None


def default_output_path(input_path: str | Path) -> Path:
    source = Path(input_path).expanduser().resolve()
    return source.with_name(f"{source.stem}_mcnp_report.xlsx")


def resolve_output_path(input_path: str | Path, requested: str | None, overwrite: bool) -> Path:
    source = Path(input_path).expanduser().resolve()
    if requested:
        output = Path(requested).expanduser().resolve()
        if output.suffix.lower() != ".xlsx":
            raise ConfigurationError("输出文件必须使用 .xlsx 扩展名。")
        if output.exists() and not overwrite:
            raise ConfigurationError(f"输出已存在：{output}；请改用其他路径或启用覆盖。")
        return output
    output = default_output_path(source)
    if output.exists() and not overwrite:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = source.with_name(f"{source.stem}_mcnp_report_{stamp}.xlsx")
    return output


def analyze_file(request: AnalysisRequest, progress: ProgressCallback | None = None) -> AnalysisOutcome:
    if request.ai_mode not in {"auto", "off", "required"}:
        raise ConfigurationError(f"无效 AI 模式：{request.ai_mode}")
    source = Path(request.input_path).expanduser().resolve()
    destination = resolve_output_path(source, request.output_path, request.overwrite)
    notify = progress or (lambda stage, message: None)
    notify("parse", f"正在流式解析 {source.name}")
    result = None
    try:
        result = parse_output(source, strict=request.strict)
        notify("ai", f"正在生成中文解读（{request.ai_mode}）")
        config = load_config(request.config_path)
        profile = None if request.ai_mode == "off" else select_profile(config, request.profile)
        ai_result = generate_ai(result, profile, request.ai_mode)
        notify("excel", f"正在写入 Excel：{destination.name}")
        write_report(result, ai_result, destination)
        tally = result.tally_summaries[0] if result.tally_summaries else None
        outcome = AnalysisOutcome(
            output_path=destination,
            tally_rows=result.store.tally_count(),
            tfc_points=len(result.tfc_points),
            warning_count=result.metadata.warning_count,
            ai_provider=ai_result.provider,
            ai_status=ai_result.status,
            ai_error=ai_result.error,
            nps=result.metadata.nps,
            tally_total=tally.total if tally else None,
            relative_error=tally.relative_error if tally else None,
        )
        notify("done", f"已生成 {destination}")
        return outcome
    finally:
        if result is not None:
            result.close()
