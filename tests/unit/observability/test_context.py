import asyncio

import pytest

from relaykit.observability.context import (
    get_request_id,
    reset_request_id,
    set_request_id,
)


def test_request_id_defaults_to_none_and_resets_to_previous_state() -> None:
    assert get_request_id() is None

    token = set_request_id("req_123")
    assert get_request_id() == "req_123"

    reset_request_id(token)
    assert get_request_id() is None


def test_nested_request_id_reset_restores_outer_value() -> None:
    outer_token = set_request_id("req_outer")

    try:
        inner_token = set_request_id("req_inner")

        try:
            assert get_request_id() == "req_inner"
        finally:
            reset_request_id(inner_token)

        assert get_request_id() == "req_outer"
    finally:
        reset_request_id(outer_token)

    assert get_request_id() is None


@pytest.mark.asyncio
async def test_concurrent_tasks_keep_request_ids_isolated() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_tasks = asyncio.Event()

    async def observe_request_id(
        request_id: str,
        started: asyncio.Event,
    ) -> tuple[str | None, str | None]:
        token = set_request_id(request_id)

        try:
            started.set()
            await release_tasks.wait()
            value_during_request = get_request_id()
        finally:
            reset_request_id(token)

        return value_during_request, get_request_id()

    first_task = asyncio.create_task(
        observe_request_id("req_A", first_started)
    )
    second_task = asyncio.create_task(
        observe_request_id("req_B", second_started)
    )

    await first_started.wait()
    await second_started.wait()
    release_tasks.set()

    first_result, second_result = await asyncio.gather(
        first_task,
        second_task,
    )

    assert first_result == ("req_A", None)
    assert second_result == ("req_B", None)
    assert get_request_id() is None
