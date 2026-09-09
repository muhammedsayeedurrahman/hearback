"""A "yes" only settles the question that was actually asked."""

from __future__ import annotations

import pytest

from engine.confirmation import challenged_by, spoken_numbers
from engine.models import Candidate, Delivered, FactStatus
from engine.state import apply_extraction, new_session, next_epoch, record_delivery, verify


def _fact_after_readback(value: str = "10 mg", heard: str | None = None, field: str = "morphine_dose"):
    """A critical fact that has been read back to the listener and awaits a confirmation."""
    state = next_epoch(new_session("s"), "we gave it", at_ms=0)
    state = apply_extraction(state, [Candidate(field, value)], epoch=1, at_ms=1)
    delivered = Delivered(
        text_heard=heard if heard is not None else f"Confirming. morphine, {value.split()[0]} milligrams.",
        complete=True,
    )
    return record_delivery(state, field, delivered, at_ms=2, speech_epoch=1)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ninety over sixty", ("90", "60")),
        ("90/60", ("90", "60")),
        ("five milligrams", ("5",)),
        ("0.5 mg", ("0.5",)),
        ("5.0 mg", ("5",)),
        ("three hundred milligrams", ("300",)),
        ("twenty five milligrams", ("25",)),
        ("yes, that's right", ()),
    ],
)
def test_spoken_numbers_reads_speech_and_text_the_same_way(text, expected):
    assert spoken_numbers(text) == expected


def test_a_bare_yes_confirms_whatever_was_read_back():
    state = _fact_after_readback()
    assert challenged_by(state.fact("morphine_dose"), "Yes, that's right.") is None


def test_repeating_the_value_that_was_read_back_is_a_confirmation():
    state = _fact_after_readback()
    assert challenged_by(state.fact("morphine_dose"), "Yes, ten milligrams.") is None


def test_a_yes_carrying_a_number_that_was_never_read_back_is_challenged():
    state = _fact_after_readback()
    reason = challenged_by(state.fact("morphine_dose"), "Yes, five milligrams is correct.")
    assert reason is not None
    assert "5" in reason and "morphine_dose" in reason


def test_the_challenge_leaves_the_fact_unverified_and_says_why():
    """The whole point: a mishearing dressed as agreement must not reach the relay gate."""
    state = _fact_after_readback()
    after = verify(state, "morphine_dose", at_ms=3, spoken="Yes, five milligrams is correct.")

    assert after.fact("morphine_dose").status is FactStatus.HEARD
    event = after.events[-1]
    assert event.type == "confirmation_challenged"
    assert "never read back" in event.data["reason"]


def test_a_confirmation_that_agrees_still_verifies():
    state = _fact_after_readback()
    after = verify(state, "morphine_dose", at_ms=3, spoken="Yes, ten milligrams is correct.")
    assert after.fact("morphine_dose").status is FactStatus.VERIFIED


def test_a_confirmation_may_quote_a_number_from_a_cut_off_read_back():
    """After a barge-in the listener heard only part of the sentence; that part still counts."""
    state = _fact_after_readback(value="5 mg", heard="I had said, Confirming. morphine, 10")
    assert challenged_by(state.fact("morphine_dose"), "Yes, five milligrams.") is None
    assert challenged_by(state.fact("morphine_dose"), "Yes, ten milligrams.") is None
    assert challenged_by(state.fact("morphine_dose"), "Yes, fifty milligrams.") is not None


def test_without_the_spoken_turn_verify_behaves_as_before():
    """An operator clicking Confirm next to a displayed value has confirmed that value."""
    state = _fact_after_readback()
    assert verify(state, "morphine_dose", at_ms=3).fact("morphine_dose").status is FactStatus.VERIFIED
