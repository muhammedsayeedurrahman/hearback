"""Hearback truth-state engine.

Pure Python, no I/O. Every function returns a new immutable object; nothing is mutated.
The engine owns canonical state, transitions, the epoch fence, the heard ledger and the
relay gate. The LLM only extracts candidates and never decides what is allowed through.
"""

from engine.models import (
    Candidate,
    Delivered,
    Event,
    Fact,
    FactStatus,
    FactVersion,
    TruthState,
)

__all__ = [
    "Candidate",
    "Delivered",
    "Event",
    "Fact",
    "FactStatus",
    "FactVersion",
    "TruthState",
]
