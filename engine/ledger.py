"""Heard-State Ledger.

Rime ws3 word timestamps × playout clock × interruption instant → the exact word at which the
listener stopped hearing. Pure computation; the agent supplies the timings.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.models import Delivered


@dataclass(frozen=True)
class WordTiming:
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class SpeechRecord:
    """One agent utterance as sent to TTS, with the facts it talks about."""

    epoch: int
    text: str
    words: tuple[WordTiming, ...]
    fields: tuple[str, ...]


def words_from_rime(words: list[str], starts: list[float], ends: list[float], offset_ms: int = 0) -> tuple[WordTiming, ...]:
    """Convert a Rime ws3 `timestamps` event (seconds from synthesis start) to WordTiming."""
    if not (len(words) == len(starts) == len(ends)):
        raise ValueError("Rime timestamp arrays must be index-aligned")
    return tuple(
        WordTiming(word=w, start_ms=int(round(s * 1000)) + offset_ms, end_ms=int(round(e * 1000)) + offset_ms)
        for w, s, e in zip(words, starts, ends)
    )


def cut(words: tuple[WordTiming, ...], interrupted_at_ms: int | None) -> Delivered:
    """Return what was heard up to the interruption instant.

    A word counts as heard once it has started playing: a listener hears "ten" even when cut
    halfway through it, which is exactly why the reconciliation must mention it.
    """
    if interrupted_at_ms is None:
        return Delivered(text_heard=" ".join(w.word for w in words), complete=True)
    heard = [w for w in words if w.start_ms < interrupted_at_ms]
    if not heard:
        return Delivered(text_heard="", cutoff_word=None, cutoff_ms=interrupted_at_ms, complete=False)
    return Delivered(
        text_heard=" ".join(w.word for w in heard),
        cutoff_word=heard[-1].word,
        cutoff_ms=interrupted_at_ms,
        complete=len(heard) == len(words),
    )


def cut_from_text(full_text: str, heard_text: str) -> Delivered:
    """Fallback when only the truncated transcript is known (LiveKit aligned transcript)."""
    heard = heard_text.strip()
    if not heard:
        return Delivered(text_heard="", cutoff_word=None, complete=False)
    complete = heard.split() == full_text.strip().split()
    return Delivered(text_heard=heard, cutoff_word=heard.split()[-1], complete=complete)


def estimate_words(text: str, duration_ms: int) -> tuple[WordTiming, ...]:
    """Playout-clock estimate when Rime timestamps are unavailable (documented accuracy drop)."""
    tokens = text.split()
    if not tokens:
        return ()
    per_word = duration_ms / len(tokens)
    return tuple(
        WordTiming(word=t, start_ms=int(i * per_word), end_ms=int((i + 1) * per_word))
        for i, t in enumerate(tokens)
    )
