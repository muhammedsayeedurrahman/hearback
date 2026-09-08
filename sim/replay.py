"""Deterministic replay of a scripted handover.

Runs a whole conversation against a real sidecar in-process: no microphone, no network, no API
keys. It is how the barge-in behaviour is regression-tested in CI, how the evidence numbers are
produced, and how the demo can be shown when the venue wi-fi fails.

The agent's speech is simulated, and says so: without Rime the word timings are estimated from
the text rather than measured, which the report labels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from agent.client import HearbackClient, NextLine
from api.extraction import RuleExtractor
from api.main import create_app
from api.settings import Settings
from engine.dialogue import is_affirmation, is_negation


@dataclass(frozen=True)
class Turn:
    """One thing the paramedic says. `barge_in_at_ms` cuts the agent off mid-sentence."""

    text: str
    speaker: str = "sender"
    barge_in_at_ms: int | None = None

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Turn":
        return Turn(
            text=raw["text"],
            speaker=raw.get("speaker", "sender"),
            barge_in_at_ms=raw.get("barge_in_at_ms"),
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    turns: tuple[Turn, ...]

    @staticmethod
    def load(path: str | Path) -> "Scenario":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return Scenario(
            name=raw["name"],
            description=raw.get("description", ""),
            turns=tuple(Turn.from_dict(t) for t in raw["turns"]),
        )


@dataclass(frozen=True)
class Spoken:
    text: str
    kind: str
    fields: tuple[str, ...]
    cut_at_ms: int | None
    heard: str
    cutoff_word: str | None
    complete: bool


@dataclass(frozen=True)
class Step:
    epoch: int
    said: str
    applied: bool
    verified: tuple[str, ...]
    spoken: tuple[Spoken, ...] = ()


@dataclass(frozen=True)
class ReplayResult:
    scenario: str
    steps: tuple[Step, ...]
    relay: dict[str, Any]
    facts: dict[str, Any]
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def cutoff_words(self) -> tuple[str | None, ...]:
        return tuple(s.cutoff_word for step in self.steps for s in step.spoken if s.cut_at_ms is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "steps": [
                {
                    "epoch": s.epoch,
                    "said": s.said,
                    "applied": s.applied,
                    "verified": list(s.verified),
                    "spoken": [vars(sp) | {"fields": list(sp.fields)} for sp in s.spoken],
                }
                for s in self.steps
            ],
            "relay": self.relay,
            "facts": self.facts,
        }


def offline_settings() -> Settings:
    return Settings(
        anthropic_api_key=None,
        extraction_model="none",
        extractor="rules",
        livekit_url=None,
        livekit_api_key=None,
        livekit_api_secret=None,
        tool_delay_ms=0,
        room_prefix="replay",
        cors_origins=(),
    )


async def replay(scenario: Scenario, lang: str = "en", settings: Settings | None = None) -> ReplayResult:
    app = create_app(extractor=RuleExtractor(), settings=settings or offline_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://replay") as http:
        client = HearbackClient(client=http)
        await client.create_session("replay")
        steps = []
        for index, turn in enumerate(scenario.turns):
            nxt = scenario.turns[index + 1] if index + 1 < len(scenario.turns) else None
            steps.append(await _run_turn(client, turn, cut_at=nxt.barge_in_at_ms if nxt else None))
        relay = await client.relay(lang=lang)
        facts = (await client.state())["facts"]
    return ReplayResult(scenario=scenario.name, steps=tuple(steps), relay=relay, facts=facts)


async def _run_turn(client: HearbackClient, turn: Turn, cut_at: int | None) -> Step:
    epoch = await client.utterance(turn.text, speaker=turn.speaker)
    verified = await _confirm(client, turn.text)
    outcome = await client.extract(turn.text, epoch=epoch)

    spoken: list[Spoken] = []
    line = outcome.next_line
    while line is not None:
        # Only the first sentence of a response can be cut into: the paramedic speaks once.
        cut = cut_at if not spoken else None
        spoken.append(await _speak(client, line, epoch, cut))
        if cut is not None:
            break
        line = await client.next_line()
    return Step(
        epoch=epoch,
        said=turn.text,
        applied=outcome.applied,
        verified=verified,
        spoken=tuple(spoken),
    )


async def _confirm(client: HearbackClient, text: str) -> tuple[str, ...]:
    if is_negation(text) or not is_affirmation(text):
        return ()
    pending = await client.awaiting_confirmation()
    for field_name in pending:
        await client.verify(field_name)
    return pending


async def _speak(client: HearbackClient, line: NextLine, epoch: int, cut_at: int | None) -> Spoken:
    """Simulate speaking one sentence and report what the listener got of it."""
    payload: dict[str, Any] = {"text": line.plain, "duration_ms": _duration_ms(line.plain)}
    if cut_at is not None:
        payload["interrupted_at_ms"] = cut_at
    delivered: dict[str, Any] = {}
    for field_name in line.fields:
        body = await client.delivery(field=field_name, speech_epoch=epoch, **payload)
        delivered = body["delivered"]
    return Spoken(
        text=line.text,
        kind=line.kind,
        fields=line.fields,
        cut_at_ms=cut_at,
        heard=delivered.get("text_heard", ""),
        cutoff_word=delivered.get("cutoff_word"),
        complete=bool(delivered.get("complete")),
    )


def _duration_ms(text: str) -> int:
    from agent.ledger import MS_PER_WORD

    return max(len(text.split()) * MS_PER_WORD, 1)
