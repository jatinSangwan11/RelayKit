from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

from relaykit.observability.context import get_request_id

_RELAYKIT_LOGGER_NAME = "relaykit"
_RELAYKIT_HANDLER_NAME = "relaykit-json-stdout"

# These attributes are created by logging itself rather than by a caller's
# ``extra`` dictionary. Excluding them lets the formatter preserve only the
# application-specific context added to a record.
_STANDARD_LOG_RECORD_ATTRIBUTES = frozenset(
    {
        *logging.makeLogRecord({}).__dict__,
        "asctime",
        "message",
    }
)

_RESERVED_OUTPUT_FIELDS = frozenset(
    {
        "environment",
        "event",
        "exception",
        "level",
        "logger",
        "message",
        "service",
        "stack",
        "timestamp",
    }
)


class JsonFormatter(logging.Formatter):
    """Serialize a log record into RelayKit's stable JSON log envelope."""

    def __init__(self, *, service_name: str, environment: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        payload: dict[str, object] = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname,
            "service": self._service_name,
            "environment": self._environment,
            "logger": record.name,
            "event": getattr(record, "event", "application_log"),
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if (
                key not in _STANDARD_LOG_RECORD_ATTRIBUTES
                and key not in _RESERVED_OUTPUT_FIELDS
                and not key.startswith("_")
            ):
                payload[key] = value

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


class RequestContextFilter(logging.Filter):
    """Add request-scoped correlation context to every handled log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        # The context value is authoritative. Always assigning the field also
        # prevents a reused or manually enriched record from retaining a stale
        # request ID outside the request that produced it.
        record.requestId = get_request_id()
        return True


def configure_logging(
    *,
    level: str | int = "INFO",
    service_name: str = "relaykit-api",
    environment: str = "development",
    stream: TextIO | None = None,) -> logging.Logger:
    """Configure and return RelayKit's top-level application logger.

    Repeated calls replace only the handler managed by this function. This is
    important in development reloads and tests, where blindly adding a handler
    would duplicate every subsequent log record.
    """

    numeric_level = _resolve_log_level(level)
    output_stream = stream if stream is not None else sys.stdout
    logger = logging.getLogger(_RELAYKIT_LOGGER_NAME)

    for existing_handler in logger.handlers[:]:
        if existing_handler.get_name() == _RELAYKIT_HANDLER_NAME:
            logger.removeHandler(existing_handler)
            existing_handler.close()

    handler = logging.StreamHandler(output_stream)
    handler.set_name(_RELAYKIT_HANDLER_NAME)
    handler.setLevel(numeric_level)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        JsonFormatter(
            service_name=service_name,
            environment=environment,
        )
    )

    logger.setLevel(numeric_level)
    logger.addHandler(handler)
    logger.propagate = False
    logger.disabled = False

    return logger


def _resolve_log_level(level: str | int) -> int:
    if isinstance(level, int):
        return level

    normalized_level = level.upper()
    numeric_level = logging.getLevelNamesMapping().get(normalized_level)
    if numeric_level is None:
        raise ValueError(f"Unsupported log level: {level!r}")

    return numeric_level
