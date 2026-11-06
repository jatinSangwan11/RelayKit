from contextvars import ContextVar, Token

_request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)


def get_request_id() -> str | None:
    """Return the request ID associated with the current execution context."""

    return _request_id_context.get()


def set_request_id(request_id: str) -> Token[str | None]:
    """Set the current request ID and return a token for exact restoration."""

    return _request_id_context.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the request-ID state that existed before the matching set call."""

    _request_id_context.reset(token)
