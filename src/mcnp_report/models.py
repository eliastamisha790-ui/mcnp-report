from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator
import os
import sqlite3


@dataclass
class RunMetadata:
    source_path: str = ""
    sha256: str = ""
    file_size: int = 0
    encoding: str = "ascii"
    code_name: str = ""
    code_version: str = ""
    load_date: str = ""
    problem_id: str = ""
    input_name: str = ""
    output_name: str = ""
    mode: str = ""
    nps: int | None = None
    collisions: int | None = None
    random_numbers: int | None = None
    computer_time_minutes: float | None = None
    source_particles_per_minute: float | None = None
    termination_reason: str = ""
    normal_termination: bool = False
    warning_count: int = 0


@dataclass
class InputCard:
    source_line: int
    input_line: int
    category: str
    card: str
    raw: str
    explanation_zh: str


@dataclass
class TallySummary:
    tally_id: int
    tally_type: int
    particles: str = ""
    units: str = ""
    cell: str = ""
    volume: float | None = None
    total: float | None = None
    relative_error: float | None = None
    reported_bins: int | None = None
    zero_bins: int | None = None
    high_error_bins: int | None = None
    missed_checks: int | None = None
    source_line: int = 0


@dataclass
class TallyBin:
    seq: int
    tally_id: int
    tally_type: int
    particles: str
    cell: str
    volume: float | None
    energy_upper_mev: float | None
    result: float
    relative_error: float
    row_kind: str
    quality_flag: str
    source_line: int


@dataclass
class StatisticalCheck:
    tally_id: int
    check_no: int
    name_en: str
    name_zh: str
    desired: str
    observed: str
    passed: bool
    source_line: int


@dataclass
class TFCPoint:
    tally_id: int
    nps: int
    mean: float
    error: float
    vov: float
    slope: float
    fom: float
    source_line: int


@dataclass
class Diagnostic:
    severity: str
    source_line: int
    message_en: str
    message_zh: str
    category: str = "general"


@dataclass
class SectionCoverage:
    name: str
    start_line: int
    end_line: int
    status: str
    sha256: str
    record_count: int = 0


@dataclass
class CellRecord:
    cell: int
    material: int
    atom_density: float
    gram_density: float
    volume: float
    mass: float
    pieces: int
    importance: float
    source_line: int


@dataclass
class CrossSectionRecord:
    table: str
    length: int
    source_file: str
    description: str
    source_line: int


@dataclass
class ParticleLimitRecord:
    particle_id: int
    designator: str
    particle_name: str
    cutoff_energy: float
    maximum_energy: float
    smallest_table_maximum: float
    largest_table_maximum: float
    always_use_table_below: float
    always_use_model_above: float
    source_line: int


@dataclass
class CellActivityRecord:
    cell: int
    tracks_entering: int
    population: int
    collisions: int
    collisions_weight: float
    number_weighted_energy: float
    flux_weighted_energy: float
    average_track_weight: float
    average_track_mfp_cm: float
    source_line: int


@dataclass
class BalanceRecord:
    particle: str
    side: str
    process: str
    tracks: int
    weight: float
    energy: float
    source_line: int


@dataclass
class Table160Metric:
    tally_id: int
    name_en: str
    name_zh: str
    value: float
    source_line: int


@dataclass
class DensityBin:
    tally_id: int
    abscissa: float | None
    tally_number: int | None
    num_density: float | None
    log_density: float | None
    row_kind: str
    source_line: int


@dataclass
class AIRequest:
    facts: dict[str, Any]
    language: str = "zh-CN"
    audience: str = "核工程人员"
    prompt_version: str = "1.0"


@dataclass
class AIFinding:
    title: str
    interpretation: str
    severity: str
    fact_ids: list[str] = field(default_factory=list)


@dataclass
class AIResult:
    provider: str
    status: str
    overview: str
    findings: list[AIFinding] = field(default_factory=list)
    error: str = ""


class TempStore:
    """SQLite-backed high-cardinality rows for bounded-memory parsing."""

    def __init__(self, path: str):
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.executescript(
            """
            CREATE TABLE tally_bins (
              seq INTEGER PRIMARY KEY, tally_id INTEGER, tally_type INTEGER,
              particles TEXT, cell TEXT, volume REAL, energy_upper_mev REAL,
              result REAL, relative_error REAL, row_kind TEXT,
              quality_flag TEXT, source_line INTEGER
            );
            CREATE TABLE density_bins (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, tally_id INTEGER,
              abscissa REAL, tally_number INTEGER, num_density REAL,
              log_density REAL, row_kind TEXT, source_line INTEGER
            );
            """
        )
        self._pending = 0

    def add_tally_bin(self, row: TallyBin) -> None:
        self.connection.execute(
            "INSERT INTO tally_bins VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row.seq, row.tally_id, row.tally_type, row.particles, row.cell,
                row.volume, row.energy_upper_mev, row.result, row.relative_error,
                row.row_kind, row.quality_flag, row.source_line,
            ),
        )
        self._commit_periodically()

    def add_density_bin(self, row: DensityBin) -> None:
        self.connection.execute(
            "INSERT INTO density_bins(tally_id,abscissa,tally_number,num_density,log_density,row_kind,source_line) VALUES (?,?,?,?,?,?,?)",
            (row.tally_id, row.abscissa, row.tally_number, row.num_density, row.log_density, row.row_kind, row.source_line),
        )
        self._commit_periodically()

    def _commit_periodically(self) -> None:
        self._pending += 1
        if self._pending >= 5000:
            self.connection.commit()
            self._pending = 0

    def finalize(self) -> None:
        self.connection.commit()
        self._pending = 0

    def tally_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM tally_bins").fetchone()[0])

    def density_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM density_bins").fetchone()[0])

    def iter_tally_bins(self) -> Iterator[TallyBin]:
        cursor = self.connection.execute(
            "SELECT seq,tally_id,tally_type,particles,cell,volume,energy_upper_mev,result,relative_error,row_kind,quality_flag,source_line FROM tally_bins ORDER BY seq"
        )
        for row in cursor:
            yield TallyBin(*row)

    def iter_density_bins(self) -> Iterator[DensityBin]:
        cursor = self.connection.execute(
            "SELECT tally_id,abscissa,tally_number,num_density,log_density,row_kind,source_line FROM density_bins ORDER BY seq"
        )
        for row in cursor:
            yield DensityBin(*row)

    def close(self, delete: bool = True) -> None:
        try:
            self.connection.close()
        finally:
            if delete:
                try:
                    os.remove(self.path)
                except FileNotFoundError:
                    pass


@dataclass
class ParseResult:
    metadata: RunMetadata
    store: TempStore
    input_cards: list[InputCard] = field(default_factory=list)
    tally_summaries: list[TallySummary] = field(default_factory=list)
    statistical_checks: list[StatisticalCheck] = field(default_factory=list)
    tfc_points: list[TFCPoint] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    sections: list[SectionCoverage] = field(default_factory=list)
    cells: list[CellRecord] = field(default_factory=list)
    cross_sections: list[CrossSectionRecord] = field(default_factory=list)
    particle_limits: list[ParticleLimitRecord] = field(default_factory=list)
    cell_activity: list[CellActivityRecord] = field(default_factory=list)
    balances: list[BalanceRecord] = field(default_factory=list)
    table160_metrics: list[Table160Metric] = field(default_factory=list)
    xsdir: str = ""

    def close(self) -> None:
        self.store.close(delete=True)

    def facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {
            "run.normal_termination": self.metadata.normal_termination,
            "run.nps": self.metadata.nps,
            "run.computer_time_minutes": self.metadata.computer_time_minutes,
            "run.warning_count": self.metadata.warning_count,
            "run.version": self.metadata.code_version,
        }
        for tally in self.tally_summaries:
            prefix = f"tally.{tally.tally_id}"
            facts[f"{prefix}.total"] = tally.total
            facts[f"{prefix}.relative_error"] = tally.relative_error
            facts[f"{prefix}.reported_bins"] = tally.reported_bins
            facts[f"{prefix}.zero_bins"] = tally.zero_bins
            facts[f"{prefix}.high_error_bins"] = tally.high_error_bins
            facts[f"{prefix}.missed_checks"] = tally.missed_checks
        if self.tfc_points:
            facts["tfc.final_fom"] = self.tfc_points[-1].fom
            facts["tfc.final_error"] = self.tfc_points[-1].error
        return facts

    def as_summary_dict(self) -> dict[str, Any]:
        return {
            "metadata": asdict(self.metadata),
            "tallies": [asdict(item) for item in self.tally_summaries],
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "statistical_checks": [asdict(item) for item in self.statistical_checks],
            "facts": self.facts(),
        }

