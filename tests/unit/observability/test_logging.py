import json
import logging
import sys
from io import StringIO

import pytest

from relaykit.observability.context import reset_request_id, set_request_id
from relaykit.observability.logging import JsonFormatter, configure_logging


def test_json_formatter_emits_stable_envelope_and_custom_fields() -> None:
    formatter = JsonFormatter(
        service_name="relaykit-api",
        environment="test",
    )
    record = logging.LogRecord(
        name="relaykit.api.routes.events",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="Event %s",
        args=("accepted",),
        exc_info=None,
    )
    record.event = "event_accepted"
    record.eventId = "evt_123"
    record.deliveryCount = 2

    payload = json.loads(formatter.format(record))

    assert payload["timestamp"].endswith("Z")
    assert payload["level"] == "INFO"
    assert payload["service"] == "relaykit-api"
    assert payload["environment"] == "test"
    assert payload["logger"] == "relaykit.api.routes.events"
    assert payload["event"] == "event_accepted"
    assert payload["message"] == "Event accepted"
    assert payload["eventId"] == "evt_123"
    assert payload["deliveryCount"] == 2


def test_json_formatter_includes_exception_traceback() -> None:
    formatter = JsonFormatter(
        service_name="relaykit-api",
        environment="test",
    )

    try:
        raise RuntimeError("database unavailable")
    except RuntimeError:
        record = logging.LogRecord(
            name="relaykit.api.routes.events",
            level=logging.ERROR,
            pathname=__file__,
            lineno=52,
            msg="Event transaction failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "application_log"
    assert payload["message"] == "Event transaction failed"
    assert "RuntimeError: database unavailable" in payload["exception"]
    assert "Traceback" in payload["exception"]


def test_configure_logging_is_idempotent_and_enriches_request_context() -> None:
    output = StringIO()
    relaykit_logger = logging.getLogger("relaykit")
    previous_handlers = relaykit_logger.handlers[:]
    previous_level = relaykit_logger.level
    previous_propagate = relaykit_logger.propagate
    previous_disabled = relaykit_logger.disabled

    try:
        configure_logging(
            level="INFO",
            service_name="relaykit-api",
            environment="test",
            stream=output,
        )
        configure_logging(
            level="INFO",
            service_name="relaykit-api",
            environment="test",
            stream=output,
        )

        logger = logging.getLogger("relaykit.api.routes.events")
        token = set_request_id("req_123")

        try:
            logger.info(
                "Event accepted",
                extra={"event": "event_accepted", "eventId": "evt_123"},
            )
        finally:
            reset_request_id(token)

        logger.info(
            "Background operation completed",
            extra={"event": "background_operation_completed"},
        )

        lines = output.getvalue().splitlines()
        assert len(lines) == 2

        request_payload = json.loads(lines[0])
        assert request_payload["event"] == "event_accepted"
        assert request_payload["eventId"] == "evt_123"
        assert request_payload["requestId"] == "req_123"

        background_payload = json.loads(lines[1])
        assert background_payload["event"] == "background_operation_completed"
        assert background_payload["requestId"] is None
    finally:
        for handler in relaykit_logger.handlers[:]:
            if handler not in previous_handlers:
                relaykit_logger.removeHandler(handler)
                handler.close()
        relaykit_logger.handlers = previous_handlers
        relaykit_logger.setLevel(previous_level)
        relaykit_logger.propagate = previous_propagate
        relaykit_logger.disabled = previous_disabled


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unsupported log level"):
        configure_logging(level="VERBOSE")
