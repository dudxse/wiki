from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from typing import Any

from app.core.config import get_settings

_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
_URL_QUERY_RE = re.compile(r"(https?://\S+?)\?(\S+)")
_PATH_QUERY_RE = re.compile(r"(\s/\S+?)\?(\S+)")


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def _redact_message(message: str) -> str:
    message = _URL_QUERY_RE.sub(r"\1?redacted", message)
    return _PATH_QUERY_RE.sub(r"\1?redacted", message)


class JSONFormatter(logging.Formatter):
    """Format logs as a JSON object for better observability."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_message(record.getMessage()),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

        if request_id := get_request_id():
            log_record["request_id"] = request_id

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


class LevelToggleFilter(logging.Filter):
    """Filter log records based on per-level enable flags."""

    def __init__(
        self,
        *,
        debug: bool,
        info: bool,
        warning: bool,
        error: bool,
        critical: bool,
    ) -> None:
        super().__init__()
        self._debug = debug
        self._info = info
        self._warning = warning
        self._error = error
        self._critical = critical

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.CRITICAL:
            return self._critical
        if record.levelno >= logging.ERROR:
            return self._error
        if record.levelno >= logging.WARNING:
            return self._warning
        if record.levelno >= logging.INFO:
            return self._info
        return self._debug


def configure_logging() -> None:
    """Configure application logging using a JSON formatter."""
    settings = get_settings()
    log_level = settings.log_level.upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(
        LevelToggleFilter(
            debug=settings.log_debug_enabled,
            info=settings.log_info_enabled,
            warning=settings.log_warning_enabled,
            error=settings.log_error_enabled,
            critical=settings.log_critical_enabled,
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplication
    if root_logger.handlers:
        root_logger.handlers = []

    root_logger.addHandler(handler)

    # Ensure uvicorn loggers use the same JSON handler.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(log_level)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
