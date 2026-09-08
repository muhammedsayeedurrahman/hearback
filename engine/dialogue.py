"""What the agent says next.

A pure function of the truth state, so the sentence the paramedic hears is a consequence of the
state machine rather than of a model's mood. The LLM extracts facts; this decides whether they
need reading back, reconciling or merely noting, and in what order.

A fact's `delivered` record doubles as the memory of having spoken about it: once a readback has
been delivered, the same question is not asked again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from engine.models import VERIFIABLE, Fact, FactStatus, TruthState
from engine.readback import Readback, acknowledgement, conflict_prompt, confirm_prompt, reconciliation
from engine.slots import is_critical, ordered_fields

_AFFIRMATION = re.compile(
    r"\b(yes|yeah|yep|yup|correct|confirmed?|that'?s right|affirmative|aye|haan|ji|sahi)\b", re.IGNORECASE
)
_NEGATION = re.compile(
    r"\b(no|nope|negative|wrong|incorrect|not right|that'?s not|nahin|nahi|galat)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class Line:
    """One sentence to speak, and the facts it speaks about."""

    kind: str
    text: str
    plain: str
    fields: tuple[str, ...]
    inline_speed_alpha: str | None
    critical: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "plain": self.plain,
            "fields": list(self.fields),
            "inline_speed_alpha": self.inline_speed_alpha,
            "critical": self.critical,
        }


def is_affirmation(text: str) -> bool:
    return bool(_AFFIRMATION.search(text)) and not _NEGATION.search(text)


def is_negation(text: str) -> bool:
    return bool(_NEGATION.search(text))


def awaiting_confirmation(state: TruthState) -> tuple[str, ...]:
    """Critical facts already read back and still unverified: what a bare "yes" would confirm."""
    return tuple(
        field
        for field in ordered_fields(list(state.facts))
        if _is_awaiting(state.facts[field])
    )


def next_line(state: TruthState) -> Line | None:
    """The next thing worth saying, or None when the right move is to keep listening."""
    facts = [state.facts[f] for f in ordered_fields(list(state.facts))]
    for build in (_conflict, _reconcile, _confirm, _acknowledge):
        for fact in facts:
            line = build(fact)
            if line is not None:
                return line
    return None


def _is_awaiting(fact: Fact) -> bool:
    return is_critical(fact.field) and fact.status in VERIFIABLE and fact.current.delivered is not None


def _line(kind: str, fact: Fact, readback: Readback | None) -> Line | None:
    if readback is None:
        return None
    return Line(
        kind=kind,
        text=readback.text,
        plain=readback.plain,
        fields=(fact.field,),
        inline_speed_alpha=readback.inline_speed_alpha,
        critical=readback.critical,
    )


def _conflict(fact: Fact) -> Line | None:
    if fact.status is not FactStatus.CONFLICTED or fact.current.delivered is not None:
        return None
    return _line("conflict", fact, conflict_prompt(fact))


def _reconcile(fact: Fact) -> Line | None:
    """Only after a correction that cut into a readback the listener had already partly heard."""
    if fact.status is not FactStatus.CORRECTED or fact.current.delivered is not None:
        return None
    if not fact.history or fact.history[-1].delivered is None:
        return None
    return _line("reconcile", fact, reconciliation(fact))


def _confirm(fact: Fact) -> Line | None:
    if not is_critical(fact.field) or fact.status not in VERIFIABLE:
        return None
    if fact.current.delivered is not None:
        return None
    return _line("confirm", fact, confirm_prompt(fact))


def _acknowledge(fact: Fact) -> Line | None:
    if is_critical(fact.field) or fact.status not in VERIFIABLE:
        return None
    if fact.current.delivered is not None:
        return None
    return _line("acknowledge", fact, acknowledgement(fact))
