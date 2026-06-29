"""Shared helpers and custom exceptions."""

from __future__ import annotations


class QucsError(Exception):
    """Base exception for all qucs-mcp errors."""


class SimulationError(QucsError):
    """Raised when simulator.exe exits with a non-zero return code."""


class SimulationTimeoutError(QucsError):
    """Raised when a simulation exceeds the configured timeout."""


class ResultsParseError(QucsError):
    """Raised when a .dat file cannot be parsed."""


class QucsConfigError(QucsError):
    """Raised when QUCS_HOME cannot be resolved to a valid installation."""


def slugify_net(name: str) -> str:
    """Convert a net label to a valid Qucs net name (no spaces, no special chars)."""
    return name.strip().replace(" ", "_").replace("-", "_")
