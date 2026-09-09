"""Tests for the evidence harness.

A harness that scores the product has to be scored itself: a check that cannot fail is not
evidence. Each test here either feeds the checker something known-bad and expects it to complain,
or pins the arithmetic the report prints.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.acceptance import (
    FIXTURES,
    NOT_RUN,
    PASS,
    _core,
    _quoted_segment,
    _readback_problems,
    not_run,
    percentiles,
    t4_ledger,
    t5_readback,
    t7_provider,
)
from sim.rime_probe import digit_error_rate, digits_of


def test_percentiles_are_ordered_and_labelled():
    stats = percentiles([10.0, 20.0, 30.0, 40.0, 500.0])
    assert stats["n"] == 5
    assert stats["min_ms"] <= stats["p50_ms"] <= stats["p90_ms"] <= stats["max_ms"]
    assert stats["p50_ms"] == 30.0


def test_percentiles_of_nothing_is_empty_not_zero():
    assert percentiles([]) == {}


def test_not_run_carries_its_reason():
    result = not_run("T1", "Time-to-silence", "P90 <= 300 ms", "needs a Rime key")
    assert result.status == NOT_RUN
    assert "Rime key" in result.note
    assert result.measured == {}


def test_quoted_segment_is_only_the_claim_about_what_was_heard():
    line = "I had said, Confirming. morphine, 10 milligrams. You're now saying 5 milligrams. Use 5 as final?"
    assert _quoted_segment(line).strip() == "Confirming. morphine, 10 milligrams."


def test_quoted_segment_empty_when_nothing_was_quoted():
    assert _quoted_segment("I had said 10 milligrams. You're now saying 5 milligrams.") == ""


def test_core_ignores_punctuation_not_words():
    assert _core("morphine,") == _core("Morphine.")
    assert _core("ten") != _core("tenth")


def test_readback_checker_catches_an_unspelled_look_alike_drug():
    item = {"id": "x", "field": "morphine_dose", "value": "5 mg", "kind": "lasa_dose"}
    problems = _readback_problems(item, "5 milligrams", "[5] milligrams, spell(5) milligrams")
    assert any("not spelled" in p for p in problems)


def test_readback_checker_catches_markup_leaking_into_the_plain_variant():
    item = {"id": "x", "field": "hr", "value": "128", "kind": "noted"}
    problems = _readback_problems(item, "Heart rate noted as spell(128).", "Heart rate noted as 128.")
    assert any("variant A carries markup" in p for p in problems)


def test_readback_checker_catches_a_slash_read_as_a_slash():
    item = {"id": "x", "field": "bp", "value": "90/60", "kind": "pair"}
    problems = _readback_problems(item, "90 over 60", "[90]/[60]")
    assert any("'over'" in p for p in problems)


def test_t5_passes_on_the_committed_fixture():
    result = t5_readback(FIXTURES / "pronunciation_30.json")
    assert result.status == PASS, result.failures
    assert result.runs == 30


def test_t4_passes_on_the_committed_annotations():
    result = t4_ledger(FIXTURES / "ledger_annotations.json")
    assert result.status == PASS, result.failures
    assert result.measured["annotated_cuts"] >= 20


def test_t4_reports_a_miss_rather_than_hiding_it(tmp_path: Path):
    """A deliberately wrong annotation must show up as a failure, not be rounded away."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        """{"sentences": [{"id": "X", "text": "one two three four",
        "words": ["one", "two", "three", "four"],
        "start": [0.0, 0.4, 0.8, 1.2], "end": [0.38, 0.78, 1.18, 1.6],
        "cuts": [{"offset_ms": 500, "expected_word": "four"}]}]}""",
        encoding="utf-8",
    )
    result = t4_ledger(bad)
    assert result.status == "FAIL"
    assert result.failures[0]["got"] == "two"
    assert result.failures[0]["words_off"] == 2


async def test_t7_observes_a_real_provider_switch():
    result = await t7_provider()
    assert result.status == PASS, result.failures
    assert result.measured["provider_events"] >= 2


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("ninety over sixty", "9060"),
        ("90/60", "9060"),
        ("five milligrams", "5"),
        ("three hundred milligrams", "300"),
        ("M R N A four seven two", "472"),
        ("no numbers here", ""),
    ],
)
def test_digits_of_reduces_speech_and_text_to_the_same_digits(spoken: str, expected: str):
    assert digits_of(spoken) == expected


def test_digit_error_rate_is_zero_when_the_number_survives_the_round_trip():
    assert digit_error_rate("90/60", "blood pressure ninety over sixty") == 0.0


def test_digit_error_rate_counts_a_misheard_digit():
    assert digit_error_rate("90/60", "blood pressure ninety over fifty") > 0.0
