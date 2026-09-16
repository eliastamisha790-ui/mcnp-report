class McnpReportError(Exception):
    """Base exception for the application."""


class UnsupportedVersionError(McnpReportError):
    """The input is not the explicitly supported MCNP6 1.0 format."""


class PartialParseError(McnpReportError):
    """Strict parsing found missing required data or unknown sections."""


class ConfigurationError(McnpReportError):
    """The CLI or AI configuration is invalid."""


class AIProviderError(McnpReportError):
    """The configured AI provider failed."""


class WorkbookError(McnpReportError):
    """The Excel report could not be written."""

