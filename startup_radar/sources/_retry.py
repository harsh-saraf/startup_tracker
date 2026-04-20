"""Tiny retry helper for source network calls. ~40 LOC, no deps.

Rationale: ``docs/CRITIQUE_APPENDIX.md`` §7 rules out ``tenacity`` /
``backoff`` — the general-purpose retry libraries carry more surface area
than our three-line needs. Exponential backoff on a fixed tuple, stops on
a fixed exception list, logs at WARNING on each retry. Nothing more.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from startup_radar.observability.logging import get_logger

# Module-level alias so tests can replace it via
# `monkeypatch.setattr("startup_radar.sources._retry._sleep", ...)` without
# clobbering `time.sleep` process-wide (which freezes Streamlit's AppTest
# poll loop and any other polling code).
_sleep = time.sleep

T = TypeVar("T")

_DEFAULT_BACKOFF: tuple[float, ...] = (1.0, 2.0, 4.0)
_DEFAULT_ATTEMPTS: int = 3

log = get_logger(__name__)


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    backoff: tuple[float, ...] = _DEFAULT_BACKOFF,
    on: tuple[type[BaseException], ...] = (Exception,),
    context: dict[str, object] | None = None,
) -> T:
    """Call ``fn()``; on any exception in ``on`` retry up to ``attempts-1`` times.

    ``backoff[i]`` is the sleep before the ``i+1``-th attempt (0-indexed).
    If ``backoff`` is shorter than ``attempts-1``, the last value repeats.
    ``context`` is merged into each retry log line.
    """
    assert attempts >= 1
    ctx = context or {}
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except on as e:
            last = e
            if i == attempts - 1:
                break
            delay = backoff[min(i, len(backoff) - 1)]
            log.warning(
                "retry.backoff",
                attempt=i + 1,
                of=attempts,
                sleep_s=delay,
                err=type(e).__name__,
                **ctx,
            )
            _sleep(delay)
    assert last is not None
    raise last
