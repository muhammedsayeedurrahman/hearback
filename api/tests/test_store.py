import asyncio

import pytest

from api.store import SessionNotFound, SessionStore
from engine.state import next_epoch


async def _store_with_session(session_id: str = "s") -> SessionStore:
    store = SessionStore()
    await store.create(session_id)
    return store


async def test_unknown_session_raises_rather_than_inventing_one():
    store = SessionStore()
    with pytest.raises(SessionNotFound):
        store.get("nope")


async def test_subscriber_receives_the_backlog_then_live_events():
    store = await _store_with_session()
    stream = store.subscribe("s").__aiter__()
    assert (await stream.__anext__()).type == "session_created"

    waiting = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0)
    await store.apply("s", lambda state: next_epoch(state, "morphine ten", at_ms=1))
    event = await asyncio.wait_for(waiting, timeout=1)
    assert event.type == "utterance" and event.epoch == 1
    await stream.aclose()


async def test_every_subscriber_sees_the_same_transition():
    store = await _store_with_session()
    streams = [store.subscribe("s", since=1).__aiter__() for _ in range(3)]
    waiting = [asyncio.ensure_future(s.__anext__()) for s in streams]
    await asyncio.sleep(0)
    await store.apply("s", lambda state: next_epoch(state, "bp ninety over sixty", at_ms=2))
    events = await asyncio.wait_for(asyncio.gather(*waiting), timeout=1)
    assert [e.type for e in events] == ["utterance"] * 3
    for stream in streams:
        await stream.aclose()


async def test_closing_a_stream_deregisters_it():
    store = await _store_with_session()
    stream = store.subscribe("s").__aiter__()
    await stream.__anext__()
    assert store.subscriber_count("s") == 1
    await stream.aclose()
    assert store.subscriber_count("s") == 0


async def test_bounded_replay_ends_on_its_own():
    store = await _store_with_session()
    await store.apply("s", lambda state: next_epoch(state, "hello", at_ms=1))
    seen = [e.type async for e in store.subscribe("s", follow=False)]
    assert seen == ["session_created", "utterance"]
    assert store.subscriber_count("s") == 0


async def test_concurrent_utterances_never_lose_an_epoch():
    store = await _store_with_session()
    await asyncio.gather(*(store.apply("s", lambda st: next_epoch(st, "x", at_ms=0)) for _ in range(20)))
    state = store.get("s")
    assert state.epoch == 20
    assert [e.seq for e in state.events] == list(range(1, 22))


async def test_stress_settings_are_per_session():
    store = SessionStore()
    await store.create("a")
    await store.create("b")
    await store.set_stress("a", tool_delay_ms=3000)
    assert store.stress("a").tool_delay_ms == 3000
    assert store.stress("b").tool_delay_ms == 0
