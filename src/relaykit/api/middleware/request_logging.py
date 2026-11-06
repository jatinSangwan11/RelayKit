import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

from relaykit.observability.context import reset_request_id, set_request_id

_REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}", flags=re.ASCII)

logger = logging.getLogger(__name__)

CallNext = Callable[[Request], Awaitable[Response]]


async def request_logging_middleware(
    request: Request,
    call_next: CallNext,
) -> Response:
    """Correlate, time, and log one HTTP request."""

    request_id = _resolve_request_id(request.headers.get(_REQUEST_ID_HEADER))
    token = set_request_id(request_id)
    started_at = perf_counter()

    try:
        response = await call_next(request)
        duration_ms = _elapsed_milliseconds(started_at)
        response.headers[_REQUEST_ID_HEADER] = request_id

        logger.log(
            logging.ERROR if response.status_code >= 500 else logging.INFO,
            "HTTP request completed",
            extra={
                "event": "http_request_completed",
                "method": request.method,
                "path": _request_path(request),
                "statusCode": response.status_code,
                "durationMs": duration_ms,
            },
        )

        return response
    except Exception:
        logger.exception(
            "HTTP request failed",
            extra={
                "event": "http_request_failed",
                "method": request.method,
                "path": _request_path(request),
                "durationMs": _elapsed_milliseconds(started_at),
            },
        )
        raise
    finally:
        reset_request_id(token)


def _resolve_request_id(candidate: str | None) -> str:
    if candidate is not None and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate

    return f"req_{uuid4().hex}"


def _elapsed_milliseconds(started_at: float) -> float:      # pref_counter returns floating point variable values in seconds so we convert it into milliseconds
    return round((perf_counter() - started_at) * 1_000, 3)


def _request_path(request: Request) -> str:
    """Return the matched route template, or the concrete path when unmatched.

    Example: a request for ``/v1/deliveries/del_123`` may match the route
    template ``/v1/deliveries/{delivery_id}``. Logging the template groups all
    delivery-inspection requests together and avoids placing a unique delivery
    ID in every access-log path. A 404 has no matched route, so it falls back to
    the concrete requested path such as ``/does-not-exist``.
    """

    # Starlette normally adds the matched route to the ASGI scope while
    # ``call_next`` performs routing. Early failures and 404s may not have one.
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return route_path if isinstance(route_path, str) else request.url.path


"""
NOTES


datetime/LogRecord timestamp → when something happened
perf_counter               → how long it took


"""
