"""Source ABC. Every data source subclasses this and registers itself in registry.py."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from startup_radar.config import AppConfig
from startup_radar.models import Startup

if TYPE_CHECKING:
    from startup_radar.storage import Storage


class Source(ABC):
    """Pluggable data source.

    Subclasses MUST set `name` (human-readable) and `enabled_key`
    (attribute name on cfg.sources). `fetch(cfg, storage=None)` is the only
    required method; `healthcheck()` is optional and defaults to a
    pass-through (Phase 6's `startup-radar doctor` consumes it).

    The optional ``storage`` kwarg was added in Phase 10. Only sources
    that need dedup state (today just Gmail) read it; the rest ignore it.
    """

    name: str
    enabled_key: str

    @abstractmethod
    def fetch(self, cfg: AppConfig, storage: Storage | None = None) -> list[Startup]:
        """Pull records and return zero or more Startup rows.

        Transient failures (timeouts, 5xx, parse glitches) go through the
        ``log.warning → return []`` pattern from ``.claude/rules/observability.md``
        (``_retry`` already absorbs brief blips). Raise
        ``startup_radar.errors.SourceError`` only for non-transient failures the
        caller should surface to the user — the pipeline records them via
        ``storage.record_run(..., error=...)`` and the CLI boundary renders them
        as a single-line error.
        """

    def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
        """Return (ok, detail). `network=False` → filesystem/config only.

        Override per source. Default implementation always returns
        `(True, "no healthcheck defined")` so a freshly scaffolded source
        fails open rather than crashing `doctor`.
        """
        return (True, "no healthcheck defined")
