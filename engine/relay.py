"""Relay gate text builder: VERIFIED facts only, in ATMIST-AMBO order."""

from __future__ import annotations

from dataclasses import dataclass

from engine.models import Fact, TruthState
from engine.readback import NUMBER_SPEED_ALPHA, label, spoken_value
from engine.slots import completeness, is_critical, ordered_fields
from engine.state import pending, relayable

EMPTY_RELAY = "No verified facts to relay yet."


@dataclass(frozen=True)
class Relay:
    text: str
    facts: tuple[Fact, ...]
    withheld: tuple[str, ...]
    inline_speed_alpha: str | None
    completeness: dict[str, bool]


def build(state: TruthState, lang: str = "en") -> Relay:
    verified = relayable(state)
    order = ordered_fields([f.field for f in verified])
    by_field = {f.field: f for f in verified}
    lines = [_line(by_field[f]) for f in order]
    withheld = tuple(f.field for f in pending(state))
    text = _intro(lang) + " ".join(lines) if lines else EMPTY_RELAY
    return Relay(
        text=text,
        facts=tuple(by_field[f] for f in order),
        withheld=withheld,
        inline_speed_alpha=NUMBER_SPEED_ALPHA if lines else None,
        completeness=completeness([f.field for f in verified]),
    )


def _intro(lang: str) -> str:
    return "Verified handover. " if lang == "en" else ""


def _line(fact: Fact) -> str:
    name = label(fact.field)
    if is_critical(fact.field):
        return f"{name.capitalize()}, {spoken_value(fact.field, fact.value)}."
    return f"{name.capitalize()}, {fact.value}."
