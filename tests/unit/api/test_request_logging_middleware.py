import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import StringIO

import pytest
from fastapi import Request, Response
from starlette.types import Scope

from relaykit.api.middleware.request_logging import request_logging_middleware
from relaykit.observability.context import get_request_id
from relaykit.observability.logging import configure_logging

_GENERATED_REQUEST_ID_PATTERN = re.compile(r"req_[0-9a-f]{32}")


def _make_request(
    *,
    request_id: str | None = None,
    method: str = "POST",
    path: str = "/v1/events",
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode()))

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


@asynccontextmanager
async def _capture_relaykit_logs() -> AsyncIterator[StringIO]:
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
        yield output
    finally:
        for handler in relaykit_logger.handlers[:]:
            if handler not in previous_handlers:
                relaykit_logger.removeHandler(handler)
                handler.close()
        relaykit_logger.handlers = previous_handlers
        relaykit_logger.setLevel(previous_level)
        relaykit_logger.propagate = previous_propagate
        relaykit_logger.disabled = previous_disabled


@pytest.mark.asyncio
async def test_middleware_generates_request_id_and_logs_completion() -> None:
    request = _make_request()
    observed_request_id: str | None = None

    async def call_next(_: Request) -> Response:
        nonlocal observed_request_id
        observed_request_id = get_request_id()
        return Response(status_code=202)

    async with _capture_relaykit_logs() as output:
        response = await request_logging_middleware(request, call_next)

    response_request_id = response.headers["X-Request-ID"]
    payload = json.loads(output.getvalue())

    assert _GENERATED_REQUEST_ID_PATTERN.fullmatch(response_request_id)
    assert observed_request_id == response_request_id
    assert payload["requestId"] == response_request_id
    assert payload["event"] == "http_request_completed"
    assert payload["method"] == "POST"
    assert payload["path"] == "/v1/events"
    assert payload["statusCode"] == 202
    assert payload["durationMs"] >= 0
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_middleware_preserves_valid_incoming_request_id() -> None:
    request = _make_request(request_id="client-request_123")

    async def call_next(_: Request) -> Response:
        assert get_request_id() == "client-request_123"
        return Response(status_code=200)

    async with _capture_relaykit_logs() as output:
        response = await request_logging_middleware(request, call_next)

    payload = json.loads(output.getvalue())
    assert response.headers["X-Request-ID"] == "client-request_123"
    assert payload["requestId"] == "client-request_123"
    assert get_request_id() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_request_id",
    [
        "contains spaces",
        "x" * 65,
        "contains/slash",
    ],
)
async def test_middleware_replaces_invalid_request_id(
    invalid_request_id: str,
) -> None:
    request = _make_request(request_id=invalid_request_id)

    async def call_next(_: Request) -> Response:
        return Response(status_code=200)

    async with _capture_relaykit_logs() as output:
        response = await request_logging_middleware(request, call_next)

    response_request_id = response.headers["X-Request-ID"]
    payload = json.loads(output.getvalue())
    assert _GENERATED_REQUEST_ID_PATTERN.fullmatch(response_request_id)
    assert response_request_id != invalid_request_id
    assert payload["requestId"] == response_request_id


@pytest.mark.asyncio
async def test_middleware_logs_handled_error_response_as_completion() -> None:
    request = _make_request(request_id="req_validation")

    async def call_next(_: Request) -> Response:
        return Response(status_code=422)

    async with _capture_relaykit_logs() as output:
        response = await request_logging_middleware(request, call_next)

    payload = json.loads(output.getvalue())
    assert response.headers["X-Request-ID"] == "req_validation"
    assert payload["event"] == "http_request_completed"
    assert payload["level"] == "INFO"
    assert payload["statusCode"] == 422


@pytest.mark.asyncio
async def test_middleware_logs_unhandled_exception_and_resets_context() -> None:
    request = _make_request(request_id="req_failure")

    async def call_next(_: Request) -> Response:
        raise RuntimeError("unexpected failure")

    async with _capture_relaykit_logs() as output:
        with pytest.raises(RuntimeError, match="unexpected failure"):
            await request_logging_middleware(request, call_next)

    payload = json.loads(output.getvalue())
    assert payload["event"] == "http_request_failed"
    assert payload["level"] == "ERROR"
    assert payload["requestId"] == "req_failure"
    assert "RuntimeError: unexpected failure" in payload["exception"]
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_concurrent_middleware_calls_keep_request_ids_isolated() -> None:
    both_started = asyncio.Event()
    started_count = 0

    async def call_next(request: Request) -> Response:
        nonlocal started_count
        started_count += 1
        if started_count == 2:
            both_started.set()
        await both_started.wait()
        assert get_request_id() == request.headers["X-Request-ID"]
        return Response(status_code=200)

    first_request = _make_request(request_id="req_A")
    second_request = _make_request(request_id="req_B")

    async with _capture_relaykit_logs() as output:
        first_response, second_response = await asyncio.gather(
            request_logging_middleware(first_request, call_next),
            request_logging_middleware(second_request, call_next),
        )

    payloads = [json.loads(line) for line in output.getvalue().splitlines()]
    payloads_by_request_id = {
        payload["requestId"]: payload for payload in payloads
    }

    assert first_response.headers["X-Request-ID"] == "req_A"
    assert second_response.headers["X-Request-ID"] == "req_B"
    assert set(payloads_by_request_id) == {"req_A", "req_B"}
    assert get_request_id() is None
