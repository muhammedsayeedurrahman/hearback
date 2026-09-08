"""Barge-in sweep.

Cuts the agent off at each offset and checks the invariant the product rests on: whatever the
agent says afterwards about what the listener heard must match what was actually delivered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sim.replay import Scenario, Turn, replay


@dataclass(frozen=True)
class Probe:
    offset_ms: int
    cutoff_word: str | None
    heard: str
    complete: bool
    quoted_back: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset_ms": self.offset_ms,
            "cutoff_word": self.cutoff_word,
            "heard": self.heard,
            "complete": self.complete,
            "quoted_back": self.quoted_back,
        }


def with_offset(scenario: Scenario, offset_ms: int) -> Scenario:
    turns = tuple(
        Turn(text=t.text, speaker=t.speaker, barge_in_at_ms=offset_ms if t.barge_in_at_ms is not None else None)
        for t in scenario.turns
    )
    return Scenario(name=f"{scenario.name} @ {offset_ms} ms", description=scenario.description, turns=turns)


async def probe(scenario: Scenario, offset_ms: int) -> Probe:
    result = await replay(with_offset(scenario, offset_ms))
    cut = next((s for step in result.steps for s in step.spoken if s.cut_at_ms is not None), None)
    reconcile = next((s for step in result.steps for s in step.spoken if s.kind == "reconcile"), None)
    heard = cut.heard if cut else ""
    quoted = bool(reconcile and heard and heard.rstrip(" .,;") in reconcile.text)
    return Probe(
        offset_ms=offset_ms,
        cutoff_word=cut.cutoff_word if cut else None,
        heard=heard,
        complete=bool(cut and cut.complete),
        quoted_back=quoted or not heard,
    )
