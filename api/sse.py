"""Server-sent events for the dashboard.

The dashboard must be able to reconnect mid-handover without losing the story, so the stream
replays from a caller-supplied sequence number and then continues live. Idle connections emit a
comment line so proxies do not drop a session that is simply listening.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from api.store import SessionStore
from engine.models import Event

KEEPALIVE_SECONDS = 15.0


def format_event(event: Event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.to_dict())}\n\n"


async def event_stream(
    store: SessionStore, session_id: str, since: int = 0, follow: bool = True
) -> AsyncIterator[str]:
    """Yield SSE frames until the backlog runs out (follow=False) or the client disconnects."""
    events = store.subscribe(session_id, since, follow=follow).__aiter__()
    pending: asyncio.Task[Event] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(events.__anext__())
            try:
                event = await asyncio.wait_for(asyncio.shield(pending), KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            except StopAsyncIteration:
                return
            pending = None
            yield format_event(event)
    finally:
        if pending is not None:
            # cancel() only *requests* cancellation. Until the task has actually processed it the
            # subscription is still executing __anext__, and closing a generator in that state
            # raises "aclose(): asynchronous generator is already running" - which is what a
            # browser leaving mid-handover used to put in the log. asyncio.wait returns once the
            # task is done and, unlike awaiting it, does not re-raise what it was cancelled with.
            pending.cancel()
            await asyncio.wait({pending})
        await events.aclose()
