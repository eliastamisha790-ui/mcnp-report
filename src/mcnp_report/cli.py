from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from . import __version__
from .config import user_config_path
from .errors import AIProviderError, ConfigurationError, PartialParseError, UnsupportedVersionError, WorkbookError
from .service import AnalysisRequest, analyze_file


EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_INPUT = 3
EXIT_STRICT = 4
EXIT_EXCEL = 5
EXIT_AI = 6


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcnp-report",
        description="将 MCNP6, 1.0 固定源 .out 输出解析为专业中文 Excel 报告。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="解析一个 MCNP .out 文件")
    analyze.add_argument("input", metavar="INPUT", help="MCNP .out 文件")
    analyze.add_argument("-o", "--output", help="输出 .xlsx 路径；默认保存在输入文件旁")
    analyze.add_argument("--ai", choices=("auto", "off", "required"), default="auto", help="AI 解读策略，默认 auto")
    analyze.add_argument("--profile", help="AI profile 名称")
    analyze.add_argument("--config", help="指定 TOML 配置文件")
    analyze.add_argument("--strict", action="store_true", help="缺失必要段或出现未识别分页段时失败")
    analyze.add_argument("--overwrite", action="store_true", help="允许覆盖既有输出")

    init = sub.add_parser("init-config", help="创建用户配置示例")
    init.add_argument("--force", action="store_true", help="覆盖已有用户配置")
    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] not in {"analyze", "init-config", "-h", "--help", "--version"} and not argv[0].startswith("-"):
        return ["analyze", *argv]
    return argv


def _init_config(force: bool) -> int:
    destination = user_config_path()
    if destination.exists() and not force:
        raise ConfigurationError(f"用户配置已存在：{destination}；如需覆盖请加 --force。")
    source = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "config.example.toml"
    if not source.is_file():
        source = Path.cwd() / "config.example.toml"
    if not source.is_file():
        raise ConfigurationError("找不到内置 config.example.toml。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"已创建配置：{destination}")
    return EXIT_OK


def _analyze(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    labels = {"parse": "1/3", "ai": "2/3", "excel": "3/3", "done": "完成"}
    outcome = analyze_file(AnalysisRequest(
        input_path=str(source), output_path=args.output, ai_mode=args.ai,
        profile=args.profile, config_path=args.config, strict=args.strict, overwrite=args.overwrite,
    ), lambda stage, message: print(f"[{labels.get(stage, stage)}] {message}"))
    print(f"提取 {outcome.tally_rows:,} 条 tally 结果，{outcome.tfc_points} 个 TFC 点，{outcome.warning_count} 条警告。")
    if outcome.ai_error:
        print(f"AI 未可用，已使用本地规则结论：{outcome.ai_error}", file=sys.stderr)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args_list = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    parser = _parser()
    args = parser.parse_args(args_list)
    if not args.command:
        parser.print_help()
        return EXIT_CONFIG
    try:
        if args.command == "init-config":
            return _init_config(args.force)
        return _analyze(args)
    except ConfigurationError as exc:
        print(f"配置错误：{exc}", file=sys.stderr); return EXIT_CONFIG
    except UnsupportedVersionError as exc:
        print(f"输入错误：{exc}", file=sys.stderr); return EXIT_INPUT
    except PartialParseError as exc:
        print(f"严格解析失败：{exc}", file=sys.stderr); return EXIT_STRICT
    except WorkbookError as exc:
        print(f"Excel 写入失败：{exc}", file=sys.stderr); return EXIT_EXCEL
    except AIProviderError as exc:
        print(f"必需 AI 调用失败：{exc}", file=sys.stderr); return EXIT_AI
    except OSError as exc:
        print(f"文件错误：{exc}", file=sys.stderr); return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
