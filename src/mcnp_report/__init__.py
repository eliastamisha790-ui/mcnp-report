"""MCNP6 1.0 output report generator."""

from .parser import parse_output
from .report import write_report

__all__ = ["parse_output", "write_report"]
__version__ = "0.2.1"
