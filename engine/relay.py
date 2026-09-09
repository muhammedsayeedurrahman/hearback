"""Relay gate text builder: VERIFIED facts only, in ATMIST-AMBO order."""

from __future__ import annotations

from dataclasses import dataclass

from engine.models import Fact, TruthState
from engine.readback import NUMBER_SPEED_ALPHA, display_label, plain_value, spoken_value
from engine.slots import completeness, is_critical, is_identifier, ordered_fields
from engine.state import pending, relayable

EMPTY_RELAY = "No verified facts to relay yet."


@dataclass(frozen=True)
class Relay:
    text: str
    plain: str
    facts: tuple[Fact, ...]
    withheld: tuple[str, ...]
    inline_speed_alpha: str | None
    completeness: dict[str, bool]


def build(state: TruthState, lang: str = "en") -> Relay:
    verified = relayable(state)
    order = ordered_fields([f.field for f in verified])
    by_field = {f.field: f for f in verified}
    lines = [_line(by_field[f]) for f in order]
    plain_lines = [_line(by_field[f], plain=True) for f in order]
    withheld = tuple(f.field for f in pending(state))
    text = _intro(lang) + " ".join(lines) if lines else EMPTY_RELAY
    plain = _intro(lang) + " ".join(plain_lines) if plain_lines else EMPTY_RELAY
    return Relay(
        text=text,
        plain=plain,
        facts=tuple(by_field[f] for f in order),
        withheld=withheld,
        inline_speed_alpha=NUMBER_SPEED_ALPHA if lines else None,
        completeness=completeness([f.field for f in verified]),
    )


def _intro(lang: str) -> str:
    return "Verified handover. " if lang == "en" else ""


def _line(fact: Fact, plain: bool = False) -> str:
    """The relay is built twice: marked up for Rime, and as words for the record."""
    name = display_label(fact.field)
    if not (is_critical(fact.field) or is_identifier(fact.field)):
        return f"{name}, {fact.value}."
    render = plain_value if plain else spoken_value
    return f"{name}, {render(fact.field, fact.value)}."
