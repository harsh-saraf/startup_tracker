"""Source ABC. Every data source subclasses this and registers itself in registry.py."""

from __future__ import annotations

from abc import ABC, abstractmethod

from startup_radar.config import AppConfig
from startup_radar.models import Startup


class Source(ABC):
    """Pluggable data source.

    Subclasses MUST set `name` (human-readable) and `enabled_key`
    (attribute name on cfg.sources). `fetch(cfg)` is the only required
    method; `healthcheck()` is optional and defaults to a pass-through
    (Phase 6's `startup-radar doctor` consumes it).
    """

    name: str
    enabled_key: str

    @abstractmethod
    def fetch(self, cfg: AppConfig) -> list[Startup]:
        """Pull records and return zero or more Startup rows.

        On failure, log at WARNING and return []. Never raise out of
        this method — the orchestrator should never see a partial
        crash that aborts the whole run.
        """

    def healthcheck(self, cfg: AppConfig, *, network: bool = False) -> tuple[bool, str]:
        """Return (ok, detail). `network=False` → filesystem/config only.

        Override per source. Default implementation always returns
        `(True, "no healthcheck defined")` so a freshly scaffolded source
        fails open rather than crashing `doctor`.
        """
        return (True, "no healthcheck defined")
