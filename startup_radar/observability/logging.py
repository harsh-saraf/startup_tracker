"""structlog pipeline. One entry point: ``configure_logging(json: bool)``.

Called once per process — CLI ``@app.callback`` and dashboard ``web/app.py``
shell. Never call ``logging.basicConfig`` anywhere else; structlog's stdlib
bridge owns the root logger.

JSON mode when ``CI=1`` or ``STARTUP_RADAR_LOG_JSON=1``. Pretty
``ConsoleRenderer`` locally — color-coded, aligned, human-scannable.

Pipeline shape: structlog loggers run ``shared_processors`` then
``ProcessorFormatter.wrap_for_formatter`` — which parks the event dict on
the stdlib ``LogRecord`` so the handler's ``ProcessorFormatter`` does the
actual rendering. This lets stdlib-native loggers (urllib3, feedparser)
flow through the same final renderer without double-formatting.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_HANDLER_SENTINEL = "_startup_radar_handler"


def configure_logging(*, json: bool) -> None:
    """Configure structlog + the stdlib root logger. Idempotent.

    Our handler is tagged with a sentinel attribute so re-calls swap it in
    place without touching foreign handlers (notably pytest's caplog
    `LogCaptureHandler`, which must stay attached for `caplog.records` to
    populate).
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]
    # ConsoleRenderer formats exceptions itself (and warns if `format_exc_info`
    # ran first and replaced the tuple with a plain string). JSON mode needs
    # the formatted string on the record, so run it for JSON only.
    if json:
        shared_processors.append(structlog.processors.format_exc_info)

    renderer: Any = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
    )
    setattr(handler, _HANDLER_SENTINEL, True)

    root = logging.getLogger()
    root.handlers[:] = [h for h in root.handlers if not getattr(h, _HANDLER_SENTINEL, False)]
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)


def get_logger(name: str) -> Any:
    """Thin re-export of ``structlog.get_logger`` so call-sites stay ignorant."""
    return structlog.get_logger(name)
