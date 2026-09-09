import asyncio

import pytest

from api.sse import event_stream
from api.store import SessionStore
from engine.state import next_epoch


async def _store_with_session(session_id: str = "s") -> SessionStore:
    store = SessionStore()
    await store.create(session_id)
    return store


async def test_backlog_is_replayed_then_the_stream_follows_live_events():
    store = await _store_with_session()
    stream = event_stream(store, "s")

    assert "event: session_created" in await stream.__anext__()

    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.05)
    await store.apply("s", lambda state: next_epoch(state, "morphine ten", at_ms=1))
    frame = await asyncio.wait_for(waiting, timeout=1)

    assert "event: utterance" in frame and frame.endswith("\n\n")
    await stream.aclose()


async def test_a_disconnect_while_waiting_does_not_raise():
    """A browser leaving mid-handover is the common case, not an error path.

    The stream parks on a task waiting for the next event. Cancelling that task only *requests*
    cancellation, so the underlying subscription is still executing `__anext__` when cleanup runs;
    closing it in that state raised `RuntimeError: aclose(): asynchronous generator is already
    running` and put a traceback in the log on every page reload.
    """
    store = await _store_with_session()
    stream = event_stream(store, "s")
    await stream.__anext__()

    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.05)
    waiting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert store.subscriber_count("s") == 0


async def test_the_subscription_is_released_when_the_client_closes_the_stream():
    store = await _store_with_session()
    stream = event_stream(store, "s")
    await stream.__anext__()

    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.05)
    assert store.subscriber_count("s") == 1

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await stream.aclose()

    assert store.subscriber_count("s") == 0
