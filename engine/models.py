"""Immutable data model for the truth state.

A TruthState is a snapshot. Every transition builds a new snapshot and appends an Event.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class FactStatus(str, Enum):
    HEARD = "HEARD"
    INFERRED = "INFERRED"
    CORRECTED = "CORRECTED"
    CONFLICTED = "CONFLICTED"
    VERIFIED = "VERIFIED"
    SUPERSEDED = "SUPERSEDED"


RELAYABLE = frozenset({FactStatus.VERIFIED})
VERIFIABLE = frozenset({FactStatus.HEARD, FactStatus.INFERRED, FactStatus.CORRECTED})


@dataclass(frozen=True)
class Delivered:
    """What the listener audibly received of a spoken sentence about a fact."""

    text_heard: str
    cutoff_word: str | None = None
    cutoff_ms: int | None = None
    complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_heard": self.text_heard,
            "cutoff_word": self.cutoff_word,
            "cutoff_ms": self.cutoff_ms,
            "complete": self.complete,
        }


@dataclass(frozen=True)
class FactVersion:
    value: str
    status: FactStatus
    epoch: int
    source_text: str = ""
    delivered: Delivered | None = None

    def with_status(self, status: FactStatus) -> "FactVersion":
        return replace(self, status=status)

    def with_delivered(self, delivered: Delivered) -> "FactVersion":
        return replace(self, delivered=delivered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "status": self.status.value,
            "epoch": self.epoch,
            "source_text": self.source_text,
            "delivered": self.delivered.to_dict() if self.delivered else None,
        }


@dataclass(frozen=True)
class Fact:
    field: str
    current: FactVersion
    history: tuple[FactVersion, ...] = ()
    conflict: tuple[FactVersion, ...] = ()

    @property
    def status(self) -> FactStatus:
        return self.current.status

    @property
    def value(self) -> str:
        return self.current.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            **self.current.to_dict(),
            "history": [v.to_dict() for v in self.history],
            "conflict": [v.to_dict() for v in self.conflict],
        }


@dataclass(frozen=True)
class Candidate:
    """A fact candidate produced by extraction. Not yet part of the truth state."""

    field: str
    value: str
    inferred: bool = False
    source_text: str = ""


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    epoch: int
    at_ms: int
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "type": self.type,
            "epoch": self.epoch,
            "at_ms": self.at_ms,
            "data": dict(self.data),
        }


def _frozen_mapping(m: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(m))


@dataclass(frozen=True)
class TruthState:
    session_id: str
    epoch: int = 0
    facts: Mapping[str, Fact] = field(default_factory=lambda: _frozen_mapping({}))
    events: tuple[Event, ...] = ()
    provider: str = "rime"

    def fact(self, field_name: str) -> Fact | None:
        return self.facts.get(field_name)

    def with_facts(self, facts: Mapping[str, Fact]) -> "TruthState":
        return replace(self, facts=_frozen_mapping(facts))

    def with_event(self, type_: str, at_ms: int, epoch: int | None = None, **data: Any) -> "TruthState":
        ev = Event(
            seq=len(self.events) + 1,
            type=type_,
            epoch=self.epoch if epoch is None else epoch,
            at_ms=at_ms,
            data=_frozen_mapping(data),
        )
        return replace(self, events=self.events + (ev,))

    def with_epoch(self, epoch: int) -> "TruthState":
        return replace(self, epoch=epoch)

    def with_provider(self, provider: str) -> "TruthState":
        return replace(self, provider=provider)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "epoch": self.epoch,
            "provider": self.provider,
            "facts": {k: v.to_dict() for k, v in self.facts.items()},
            "event_count": len(self.events),
        }
