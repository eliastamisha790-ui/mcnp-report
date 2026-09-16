from __future__ import annotations

import re


_STANDARD = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
_IMPLICIT = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d{2,3})$")


def parse_mcnp_number(value: str) -> float:
    """Parse ordinary or MCNP implicit-exponent numbers such as ``1.58-01``."""
    text = value.strip()
    if _STANDARD.fullmatch(text):
        return float(text)
    match = _IMPLICIT.fullmatch(text)
    if match:
        return float(f"{match.group(1)}E{match.group(2)}")
    raise ValueError(f"不是有效的 MCNP 数值: {value!r}")


def maybe_number(value: str) -> float | None:
    try:
        return parse_mcnp_number(value)
    except (TypeError, ValueError):
        return None


def maybe_int(value: str) -> int | None:
    text = value.strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    return None


def strip_asa(line: str) -> tuple[str, str]:
    """Return legacy carriage-control character and printable content."""
    if line and line[0] in {" ", "0", "1", "-", "+"}:
        return line[0], line[1:]
    return "", line

