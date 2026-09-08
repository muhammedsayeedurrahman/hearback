"""Agent-side heard-state ledger.

Rime returns word timestamps relative to the start of synthesis; the agent knows when playout
started and when the paramedic cut in. Those three give the exact word the listener was on. When
timestamps do not arrive, the tracker degrades in documented steps: the truncated transcript
LiveKit reports, then a flat estimate from the playout clock.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from engine.ledger import WordTiming, cut, cut_from_text, estimate_words
from engine.models import Delivered

Clock = Callable[[], int]

# Rime Coda at speedAlpha 0.95 averages ~2.8 words per second. Used only when no word
# timestamps arrived, to estimate how long a sentence would have taken had it finished.
MS_PER_WORD = 360


@dataclass(frozen=True)
class SpokenSentence:
    """One sentence handed to TTS, and the facts it speaks about."""

    epoch: int
    text: str
    fields: tuple[str, ...]
    started_at_ms: int
    words: tuple[WordTiming, ...] = ()

    def with_words(self, words: tuple[WordTiming, ...]) -> "SpokenSentence":
        return replace(self, words=words)


@dataclass(frozen=True)
class DeliveryReport:
    """One /delivery call: what the listener heard of this sentence, for one fact."""

    field: str
    speech_epoch: int
    delivered: Delivered
    payload: dict[str, Any]


class SpeechTracker:
    """Holds the sentence currently in the air. Replaced on each new sentence, never mutated."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._current: SpokenSentence | None = None

    @property
    def current(self) -> SpokenSentence | None:
        return self._current

    def begin(self, epoch: int, text: str, fields: Iterable[str]) -> SpokenSentence:
        self._current = SpokenSentence(
            epoch=epoch, text=text, fields=tuple(fields), started_at_ms=self._clock()
        )
        return self._current

    def add_words(self, timed: Iterable[tuple[str, float, float]]) -> None:
        """Absorb Rime word timestamps (seconds from synthesis start) for the live sentence."""
        if self._current is None:
            return
        extra = tuple(
            WordTiming(word=w.strip(), start_ms=int(round(s * 1000)), end_ms=int(round(e * 1000)))
            for w, s, e in timed
            if w.strip()
        )
        if extra:
            self._current = self._current.with_words(self._current.words + extra)

    def finish(self, interrupted: bool, heard_text: str | None = None) -> tuple[DeliveryReport, ...]:
        """Close the live sentence and report what was delivered, one entry per fact."""
        sentence = self._current
        self._current = None
        if sentence is None:
            return ()
        elapsed_ms = max(0, self._clock() - sentence.started_at_ms)
        interrupted_at = elapsed_ms if interrupted else None
        delivered, payload = _resolve(sentence, interrupted_at, heard_text, elapsed_ms)
        return tuple(
            DeliveryReport(
                field=field,
                speech_epoch=sentence.epoch,
                delivered=delivered,
                payload={"field": field, "speech_epoch": sentence.epoch, **payload},
            )
            for field in sentence.fields
        )


def _resolve(
    sentence: SpokenSentence,
    interrupted_at: int | None,
    heard_text: str | None,
    elapsed_ms: int,
) -> tuple[Delivered, dict[str, Any]]:
    if sentence.words:
        payload: dict[str, Any] = {
            "words": [{"word": w.word, "start_ms": w.start_ms, "end_ms": w.end_ms} for w in sentence.words]
        }
        if interrupted_at is not None:
            payload["interrupted_at_ms"] = interrupted_at
        return cut(sentence.words, interrupted_at), payload
    if heard_text is not None:
        return (
            cut_from_text(sentence.text, heard_text),
            {"text": sentence.text, "heard_text": heard_text},
        )
    # Last resort. An interrupted sentence never played to the end, so its full duration cannot
    # come from the playout clock; it is estimated from Coda's measured rate instead.
    duration_ms = (
        max(elapsed_ms, 1)
        if interrupted_at is None
        else max(len(sentence.text.split()) * MS_PER_WORD, elapsed_ms, 1)
    )
    payload = {"text": sentence.text, "duration_ms": duration_ms}
    if interrupted_at is not None:
        payload["interrupted_at_ms"] = interrupted_at
    return cut(estimate_words(sentence.text, duration_ms), interrupted_at), payload
