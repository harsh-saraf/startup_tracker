"""Exception taxonomy. Three classes, no more — each one has a concrete catch site."""

from __future__ import annotations

__all__ = ["StartupRadarError", "ConfigError", "SourceError"]


class StartupRadarError(Exception):
    """Base for known, user-facing failure modes raised by startup_radar."""


class ConfigError(StartupRadarError):
    """Raised when config.yaml is missing, unparseable, or fails schema validation."""


class SourceError(StartupRadarError):
    """Raised by a Source's fetch() on a non-transient failure the caller should surface."""
