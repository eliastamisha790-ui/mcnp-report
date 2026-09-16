from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import PartialParseError, UnsupportedVersionError
from .models import (
    BalanceRecord,
    CellActivityRecord,
    CellRecord,
    CrossSectionRecord,
    DensityBin,
    Diagnostic,
    InputCard,
    ParseResult,
    ParticleLimitRecord,
    RunMetadata,
    SectionCoverage,
    StatisticalCheck,
    Table160Metric,
    TallyBin,
    TallySummary,
    TempStore,
    TFCPoint,
)
from .numbers import maybe_int, maybe_number, parse_mcnp_number, strip_asa


SUPPORTED_SIGNATURE = "Code Name & Version = MCNP6, 1.0"
NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+|[+-]\d{2,3})?"


CARD_EXPLANATIONS = {
    "cell": "单元卡：定义材料、密度和由曲面围成的空间区域。",
    "surface": "曲面卡：定义几何边界及其参数。",
    "mode": "MODE 卡：指定输运粒子种类。",
    "importance": "IMP 卡：设置粒子在各单元中的重要性及终止区域。",
    "material": "材料卡：给出核素组成及原子/质量分数。",
    "source": "源定义卡：描述源粒子、位置、方向和能量分布。",
    "tally": "计数卡：定义需要统计的物理量和目标单元。",
    "energy": "能量分箱卡：定义 tally 的能量边界。",
    "nps": "NPS 卡：指定要运行的粒子历史数。",
    "transform": "坐标变换卡：定义平移和旋转。",
    "data": "数据卡：控制材料、源、计数或运行参数。",
    "blank": "空行。",
    "comment": "MCNP 注释。",
}

CHECK_NAMES = [
    ("mean behavior", "均值行为"),
    ("relative error value", "相对误差数值"),
    ("relative error decrease", "相对误差是否下降"),
    ("relative error decrease rate", "相对误差下降速率"),
    ("variance of variance value", "方差的方差数值"),
    ("variance of variance decrease", "方差的方差是否下降"),
    ("variance of variance decrease rate", "方差的方差下降速率"),
    ("figure of merit value", "品质因子数值"),
    ("figure of merit behavior", "品质因子行为"),
    ("pdf slope", "概率密度函数尾部斜率"),
]

TABLE160_ZH = {
    "normed average tally per history": "每历史归一化平均 tally",
    "unnormed average tally per history": "每历史未归一化平均 tally",
    "estimated tally relative error": "tally 估计相对误差",
    "estimated variance of the variance": "方差的方差估计",
    "relative error from zero tallies": "零 tally 对相对误差的贡献",
    "relative error from nonzero scores": "非零得分对相对误差的贡献",
    "number of nonzero history tallies": "非零历史 tally 数",
    "efficiency for the nonzero tallies": "非零 tally 效率",
    "history number of largest tally": "最大 tally 所在历史号",
    "largest unnormalized history tally": "最大未归一化历史 tally",
    "(largest tally)/(average tally)": "最大 tally /平均 tally",
    "(largest tally)/(avg nonzero tally)": "最大 tally /非零平均 tally",
    "(confidence interval shift)/mean": "置信区间偏移/均值",
    "shifted confidence interval center": "偏移后置信区间中心",
}

WARNING_ZH = {
    "physics models disabled": "物理模型已禁用。",
    "below energy cutoff": "部分 tally 能量分箱低于粒子能量截断值。",
    "has been set to a conductor": "材料已按导体处理。",
    "did not pass": "TFC 统计检查未全部通过。",
    "relative errors greater than recommended": "部分 tally 分箱相对误差高于建议值。",
}


@dataclass
class _OpenSection:
    name: str
    start: int
    status: str
    digest: object
    lines: int = 0


def _encoding(path: Path) -> str:
    with path.open("rb") as stream:
        sample = stream.read(65536)
    for encoding in ("ascii", "utf-8-sig", "gb18030", "cp1252"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    return "utf-8"


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _card_kind(card: str, category: str) -> tuple[str, str]:
    text = card.strip()
    low = text.lower()
    if not text:
        kind = "blank"
    elif low.startswith("c ") or low == "c":
        kind = "comment"
    elif low.startswith("mode"):
        kind = "mode"
    elif low.startswith("imp:"):
        kind = "importance"
    elif re.match(r"m\d+\b", low):
        kind = "material"
    elif low.startswith(("sdef", "si", "sp", "sb", "ds")):
        kind = "source"
    elif re.match(r"f\d+", low):
        kind = "tally"
    elif re.match(r"e\d+", low):
        kind = "energy"
    elif low.startswith("nps"):
        kind = "nps"
    elif low.startswith(("tr", "*tr")):
        kind = "transform"
    elif category in {"cell", "surface"}:
        kind = category
    else:
        kind = "data"
    return kind, CARD_EXPLANATIONS[kind]


def _section_name(text: str, control: str) -> tuple[str, str] | None:
    low = text.lower().strip()
    known = (
        ("mcnp     version", "运行头与输入清单"),
        ("cells", "PRINT 60 单元参数"),
        ("cross-section tables", "PRINT 100 核数据库"),
        ("particles and energy limits", "PRINT 101 粒子能量限制"),
        ("problem summary", "Problem Summary"),
        ("photon   activity in each cell", "PRINT 126 单元活性"),
        ("tally fluctuation charts", "TFC 序列"),
        ("tally", "F4 Tally"),
        ("results of 10 statistical checks", "10 项统计检查"),
        ("analysis of the results in the tally fluctuation", "PRINT 160 TFC 分析"),
        ("unnormed tally density", "PRINT 161 Tally 密度"),
        ("status of the statistical checks", "统计检查状态"),
    )
    if control == "1":
        for prefix, name in known:
            if low.startswith(prefix):
                return name, "recognized"
        if low:
            return f"未识别分页段：{text.strip()[:60]}", "unsupported"
    if low.startswith("results of 10 statistical checks"):
        return "10 项统计检查", "recognized"
    return None


def _diagnostic_zh(message: str) -> str:
    low = message.lower()
    for needle, translated in WARNING_ZH.items():
        if needle in low:
            return translated
    return "MCNP 警告：" + message.strip()


def parse_output(path: str | os.PathLike[str], strict: bool = False) -> ParseResult:
    """Stream a supported MCNP6 1.0 fixed-source output into typed records."""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".out":
        raise UnsupportedVersionError(f"输入必须是存在的 .out 文件：{source}")

    encoding = _encoding(source)
    with source.open("rb") as stream:
        header = stream.read(8192).decode(encoding, errors="replace")
    if SUPPORTED_SIGNATURE not in header:
        found = re.search(r"Code Name & Version\s*=\s*([^\r\n]+)", header, re.I)
        detail = found.group(1).strip() if found else "未识别"
        raise UnsupportedVersionError(
            f"不支持的 MCNP 输出版本：{detail}；v1 仅支持 MCNP6, 1.0 固定源输出。"
        )

    fd, database_path = tempfile.mkstemp(prefix="mcnp_report_", suffix=".sqlite3")
    os.close(fd)
    store = TempStore(database_path)
    metadata = RunMetadata(
        source_path=str(source), sha256=_file_hash(source), file_size=source.stat().st_size,
        encoding=encoding, code_name="MCNP6", code_version="1.0",
    )
    result = ParseResult(metadata=metadata, store=store)

    current = _OpenSection("文件头", 1, "recognized", hashlib.sha256())
    current_table = ""
    current_category = "data"
    current_tally: TallySummary | None = None
    tally_seq = 0
    in_tally_rows = False
    stats_desired: list[str] = []
    stats_observed: list[str] = []
    tfc_tally = 4
    source_file = ""
    awaiting_tally_volume = False
    unsupported_features: set[str] = set()
    last_line = 0

    def finish_section(end_line: int) -> None:
        nonlocal current
        if current.lines:
            result.sections.append(SectionCoverage(
                current.name, current.start, max(current.start, end_line), current.status,
                current.digest.hexdigest().upper(), current.lines,
            ))

    try:
        with source.open("rb") as stream:
            for line_no, raw_bytes in enumerate(stream, 1):
                last_line = line_no
                raw = raw_bytes.decode(encoding, errors="replace").rstrip("\r\n")
                control, text = strip_asa(raw)
                low = text.lower().strip()

                section = _section_name(text, control)
                if section and (section[0] != current.name or line_no == current.start):
                    finish_section(line_no - 1)
                    current = _OpenSection(section[0], line_no, section[1], hashlib.sha256())
                current.digest.update(raw_bytes)
                current.lines += 1

                table_match = re.search(r"print table\s+(\d+)", low)
                if table_match:
                    current_table = table_match.group(1)

                m = re.search(r"mcnp\s+version\s+(\S+)\s+ld=(\S+)", text, re.I)
                if m:
                    metadata.load_date = m.group(2)
                m = re.search(r"probid\s*=\s*(.+?)\s*$", text, re.I)
                if m and not metadata.problem_id:
                    metadata.problem_id = m.group(1).strip()
                m = re.search(r"\bi=([^\s]+)\s+o=([^\s]+)", text, re.I)
                if m:
                    metadata.input_name, metadata.output_name = m.group(1), m.group(2)

                if "warning." in low:
                    message = re.split(r"warning\.\s*", text, flags=re.I, maxsplit=1)[-1].strip()
                    result.diagnostics.append(Diagnostic("warning", line_no, message, _diagnostic_zh(message), "MCNP"))

                card_match = re.match(r"\s*(\d+)-\s*(.*)$", text)
                if card_match and current.name == "运行头与输入清单":
                    input_line = int(card_match.group(1))
                    card = card_match.group(2).rstrip()
                    c = card.strip().lower()
                    if c.startswith("c cell"):
                        current_category = "cell"
                    elif c.startswith("c surface"):
                        current_category = "surface"
                    elif c.startswith("c data"):
                        current_category = "data"
                    kind, explanation = _card_kind(card, current_category)
                    result.input_cards.append(InputCard(line_no, input_line, kind, card.strip(), raw, explanation))
                    if kind == "mode":
                        metadata.mode = card.split(None, 1)[1].strip() if len(card.split(None, 1)) > 1 else ""
                    if re.match(r"\s*(kcode|fmesh|mctal|meshtal|ptrac)\b", card, re.I):
                        unsupported_features.add(card.split()[0].upper())

                if current_table == "60":
                    fields = text.split()
                    if len(fields) >= 9 and all(maybe_number(v) is not None for v in fields[:9]):
                        result.cells.append(CellRecord(
                            cell=int(fields[1]), material=int(fields[2]), atom_density=parse_mcnp_number(fields[3]),
                            gram_density=parse_mcnp_number(fields[4]), volume=parse_mcnp_number(fields[5]),
                            mass=parse_mcnp_number(fields[6]), pieces=int(fields[7]), importance=parse_mcnp_number(fields[8]),
                            source_line=line_no,
                        ))

                if current_table == "100":
                    m = re.search(r"XSDIR used:\s*(.+)$", text, re.I)
                    if m:
                        result.xsdir = m.group(1).strip()
                    m = re.search(r"tables from file\s+(.+?)\s*$", text, re.I)
                    if m:
                        source_file = m.group(1).strip()
                    fields = text.split()
                    if len(fields) >= 2 and re.fullmatch(r"\d+\.\d+[a-z]", fields[0], re.I) and fields[1].isdigit():
                        result.cross_sections.append(CrossSectionRecord(
                            fields[0], int(fields[1]), source_file, " ".join(fields[2:]), line_no
                        ))

                if current_table == "101":
                    fields = text.split()
                    if len(fields) >= 9 and fields[0].isdigit() and all(maybe_number(v) is not None for v in fields[3:9]):
                        result.particle_limits.append(ParticleLimitRecord(
                            int(fields[0]), fields[1], fields[2], *[parse_mcnp_number(v) for v in fields[3:9]], line_no
                        ))

                m = re.search(r"run terminated when\s+(\d+)\s+particle histories were done", text, re.I)
                if m:
                    metadata.nps = int(m.group(1))
                    metadata.termination_reason = "NPS 粒子历史数达到设定值"
                    metadata.normal_termination = True
                m = re.search(r"computer time(?:\s+so far in this run|\s+in mcrun|)\s*=*\s*(%s)\s+minutes" % NUM, text, re.I)
                if m:
                    metadata.computer_time_minutes = parse_mcnp_number(m.group(1))
                m = re.search(r"source particles per minute\s+(%s)" % NUM, text, re.I)
                if m:
                    metadata.source_particles_per_minute = parse_mcnp_number(m.group(1))
                m = re.search(r"random numbers generated\s+(\d+)", text, re.I)
                if m:
                    metadata.random_numbers = int(m.group(1))
                m = re.search(r"dump no\.\s+\d+.*?coll\s*=\s*(\d+)", text, re.I)
                if m:
                    metadata.collisions = int(m.group(1))
                m = re.search(r"(\d+)\s+warning messages so far", text, re.I)
                if m:
                    metadata.warning_count = max(metadata.warning_count, int(m.group(1)))

                if current_table == "126":
                    fields = text.split()
                    if len(fields) >= 10 and fields[0].isdigit() and fields[1].isdigit():
                        nums = [maybe_number(v) for v in fields[2:10]]
                        if all(v is not None for v in nums):
                            result.cell_activity.append(CellActivityRecord(
                                int(fields[1]), int(nums[0]), int(nums[1]), int(nums[2]),
                                *[float(v) for v in nums[3:]], line_no
                            ))

                if current.name == "Problem Summary":
                    pair = re.match(
                        rf"\s*(.+?)\s+(\d+)\s+({NUM})\s+({NUM})\s{{2,}}(.+?)\s+(\d+)\s+({NUM})\s+({NUM})\s*$",
                        text,
                    )
                    if pair:
                        result.balances.extend([
                            BalanceRecord("photon", "creation", pair.group(1).strip(), int(pair.group(2)), parse_mcnp_number(pair.group(3)), parse_mcnp_number(pair.group(4)), line_no),
                            BalanceRecord("photon", "loss", pair.group(5).strip(), int(pair.group(6)), parse_mcnp_number(pair.group(7)), parse_mcnp_number(pair.group(8)), line_no),
                        ])
                    else:
                        left = re.match(rf"\s*(.+?)\s+(\d+)\s+({NUM})\s+({NUM})\s*$", text)
                        if left and not low.startswith(("number of", "total photon")):
                            result.balances.append(BalanceRecord("photon", "creation", left.group(1).strip(), int(left.group(2)), parse_mcnp_number(left.group(3)), parse_mcnp_number(left.group(4)), line_no))

                m = re.match(r"tally\s+(\d+)\s+nps\s*=\s*(\d+)", low)
                if m:
                    tfc_tally = int(m.group(1))
                    current_tally = TallySummary(tfc_tally, tfc_tally, source_line=line_no)
                    result.tally_summaries.append(current_tally)
                    metadata.nps = int(m.group(2))
                    in_tally_rows = False
                    awaiting_tally_volume = False
                if current_tally:
                    m = re.search(r"tally type\s+(\d+).*?units\s+(.+?)\s*$", text, re.I)
                    if m:
                        current_tally.tally_type = int(m.group(1)); current_tally.units = m.group(2).strip()
                    m = re.search(r"particle\(s\):\s*(.+)$", text, re.I)
                    if m:
                        current_tally.particles = m.group(1).strip()
                    m = re.match(r"\s*cell\s+(\d+)\s*$", text, re.I)
                    if m:
                        current_tally.cell = m.group(1)
                    if low == "volumes":
                        awaiting_tally_volume = True
                    if low == "energy":
                        in_tally_rows = True
                        awaiting_tally_volume = False
                    if in_tally_rows:
                        fields = text.split()
                        if len(fields) == 3 and all(maybe_number(v) is not None for v in fields):
                            tally_seq += 1
                            energy = parse_mcnp_number(fields[0]); value = parse_mcnp_number(fields[1]); error = parse_mcnp_number(fields[2])
                            flag = "零值" if value == 0 else ("高误差" if error > 0.10 else "正常")
                            store.add_tally_bin(TallyBin(
                                tally_seq, current_tally.tally_id, current_tally.tally_type,
                                current_tally.particles, current_tally.cell, current_tally.volume,
                                energy, value, error, "energy_bin", flag, line_no,
                            ))
                        elif len(fields) == 3 and fields[0].lower() == "total" and all(maybe_number(v) is not None for v in fields[1:]):
                            current_tally.total = parse_mcnp_number(fields[1])
                            current_tally.relative_error = parse_mcnp_number(fields[2])
                            tally_seq += 1
                            flag = "高误差" if current_tally.relative_error > 0.10 else "正常"
                            store.add_tally_bin(TallyBin(
                                tally_seq, current_tally.tally_id, current_tally.tally_type,
                                current_tally.particles, current_tally.cell, current_tally.volume,
                                None, current_tally.total, current_tally.relative_error,
                                "total", flag, line_no,
                            ))
                            in_tally_rows = False
                    if awaiting_tally_volume and current_tally.volume is None and len(text.split()) == 1 and maybe_number(text) is not None:
                        current_tally.volume = parse_mcnp_number(text)
                        awaiting_tally_volume = False

                if low.startswith("desired"):
                    stats_desired = text.split()[1:]
                elif low.startswith("observed"):
                    stats_observed = text.split()[1:]
                elif low.startswith("passed?"):
                    passed_tokens = text.split()[1:]
                    if len(passed_tokens) >= 10 and len(stats_desired) >= 10 and len(stats_observed) >= 10:
                        for idx, (name_en, name_zh) in enumerate(CHECK_NAMES):
                            result.statistical_checks.append(StatisticalCheck(
                                tfc_tally, idx + 1, name_en, name_zh, stats_desired[idx], stats_observed[idx],
                                passed_tokens[idx].lower() == "yes", line_no,
                            ))

                m = re.search(r"did not pass\s+(\d+)\s+of the 10 statistical checks", text, re.I)
                if m and current_tally:
                    current_tally.missed_checks = int(m.group(1))
                m = re.search(r"missed\s+(\d+)\s+of 10 tfc bin checks", text, re.I)
                if m and current_tally:
                    current_tally.missed_checks = int(m.group(1))
                m = re.search(r"(\d+)\s+tally bins had\s+(\d+)\s+bins with zeros and\s+(\d+)\s+bins with relative errors", text, re.I)
                if m and current_tally:
                    current_tally.reported_bins, current_tally.zero_bins, current_tally.high_error_bins = map(int, m.groups())

                if current_table == "160":
                    for metric, value in re.findall(r"([A-Za-z][A-Za-z0-9 ()/+-]*?)\s*=\s*(%s)" % NUM, text):
                        name = " ".join(metric.split())
                        if name.lower().startswith("analysis of the results"):
                            continue
                        key = name.lower().replace("  ", " ")
                        result.table160_metrics.append(Table160Metric(tfc_tally, name, TABLE160_ZH.get(key, "MCNP 指标：" + name), parse_mcnp_number(value), line_no))

                if current_table == "161":
                    fields = text.split()
                    if len(fields) >= 4 and maybe_number(fields[0]) is not None and maybe_int(fields[1]) is not None and maybe_number(fields[2]) is not None and maybe_number(fields[3]) is not None:
                        store.add_density_bin(DensityBin(
                            tfc_tally, parse_mcnp_number(fields[0]), int(fields[1]), parse_mcnp_number(fields[2]),
                            parse_mcnp_number(fields[3]), "bin", line_no,
                        ))
                    elif len(fields) >= 3 and fields[0].lower() == "total" and maybe_int(fields[1]) is not None and maybe_number(fields[2]) is not None:
                        store.add_density_bin(DensityBin(tfc_tally, None, int(fields[1]), parse_mcnp_number(fields[2]), None, "total", line_no))

                if current.name == "TFC 序列":
                    fields = text.split()
                    if len(fields) == 6 and fields[0].isdigit() and all(maybe_number(v) is not None for v in fields[1:]):
                        result.tfc_points.append(TFCPoint(
                            tfc_tally, int(fields[0]), *[parse_mcnp_number(v) for v in fields[1:]], line_no
                        ))

        finish_section(last_line)
        store.finalize()
        metadata.warning_count = max(metadata.warning_count, len(result.diagnostics))

        missing = []
        if metadata.nps is None: missing.append("NPS")
        if not metadata.normal_termination: missing.append("正常终止信息")
        if not result.tally_summaries or result.tally_summaries[0].total is None: missing.append("F4 tally total")
        if not result.tfc_points: missing.append("TFC")
        if missing:
            result.diagnostics.append(Diagnostic("error" if strict else "warning", 0, "Missing required fields: " + ", ".join(missing), "文件截断或缺少必要段：" + "、".join(missing), "parser"))
        unsupported = [s for s in result.sections if s.status == "unsupported"]
        unsupported_tallies = [t for t in result.tally_summaries if t.tally_type != 4 or t.tally_id != 4]
        if unsupported_features or unsupported_tallies or (metadata.mode and metadata.mode.lower() != "p"):
            parts = sorted(unsupported_features)
            if unsupported_tallies: parts.append("非 F4 tally")
            if metadata.mode and metadata.mode.lower() != "p": parts.append(f"MODE {metadata.mode}")
            result.close()
            raise UnsupportedVersionError("v1 不支持该输出特征：" + "、".join(parts))
        if strict and (missing or unsupported):
            details = ", ".join(missing) or f"{len(unsupported)} 个未识别分页段"
            result.close()
            raise PartialParseError(f"严格解析失败：{details}")
        return result
    except Exception:
        try:
            store.close(delete=True)
        except Exception:
            pass
        raise
