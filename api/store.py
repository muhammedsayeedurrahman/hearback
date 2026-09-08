"""In-memory session store with an event fan-out.

The store holds the latest snapshot per session and nothing else. Transitions are pure functions
of a snapshot, applied under a per-session lock so two concurrent requests cannot interleave and
lose an epoch bump. Every event appended by a transition is broadcast to live subscribers.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace

from engine.models import Event, TruthState
from engine.state import new_session

Transition = Callable[[TruthState], TruthState]


class SessionNotFound(KeyError):
    """Raised when a request names a session that was never created."""


@dataclass(frozen=True)
class Stress:
    """Injected latency used by the evidence fixtures. Zero in normal operation."""

    tool_delay_ms: int = 0
    extract_delay_ms: int = 0


class _Session:
    def __init__(self, state: TruthState, started_at: float, stress: Stress) -> None:
        self.state = state
        self.started_at = started_at
        self.stress = stress
        self.lock = asyncio.Lock()
        self.subscribers: set[asyncio.Queue[Event]] = set()


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def create(self, session_id: str, tool_delay_ms: int = 0) -> TruthState:
        started = time.monotonic()
        state = new_session(session_id, at_ms=0)
        self._sessions[session_id] = _Session(state, started, Stress(tool_delay_ms=tool_delay_ms))
        return state

    def get(self, session_id: str) -> TruthState:
        return self._require(session_id).state

    def subscriber_count(self, session_id: str) -> int:
        return len(self._require(session_id).subscribers)

    def stress(self, session_id: str) -> Stress:
        return self._require(session_id).stress

    def now_ms(self, session_id: str) -> int:
        session = self._require(session_id)
        return int((time.monotonic() - session.started_at) * 1000)

    async def apply(self, session_id: str, transition: Transition) -> TruthState:
        """Run a transition and broadcast whatever events it appended."""
        session = self._require(session_id)
        async with session.lock:
            before = len(session.state.events)
            new_state = transition(session.state)
            session.state = new_state
            fresh = new_state.events[before:]
            for queue in session.subscribers:
                for event in fresh:
                    queue.put_nowait(event)
            return new_state

    async def set_stress(self, session_id: str, **fields: int) -> Stress:
        session = self._require(session_id)
        async with session.lock:
            session.stress = replace(session.stress, **fields)
            return session.stress

    async def subscribe(self, session_id: str, since: int = 0, follow: bool = True) -> AsyncIterator[Event]:
        """Replay past events, then stream live ones. Registration is atomic with the replay.

        `follow=False` ends the stream after the replay, which is how the dashboard hydrates on
        first paint and how the evidence scripts snapshot a finished handover.
        """
        session = self._require(session_id)
        queue: asyncio.Queue[Event] = asyncio.Queue()
        async with session.lock:
            backlog = tuple(e for e in session.state.events if e.seq > since)
            session.subscribers.add(queue)
        try:
            for event in backlog:
                yield event
            if not follow:
                return
            seen = backlog[-1].seq if backlog else since
            while True:
                event = await queue.get()
                if event.seq > seen:
                    seen = event.seq
                    yield event
        finally:
            session.subscribers.discard(queue)

    def _require(self, session_id: str) -> _Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session
