import pytest

from engine.models import Candidate, FactStatus
from engine.state import (
    TransitionError,
    apply_extraction,
    new_session,
    next_epoch,
    relayable,
    resolve_conflict,
    set_provider,
    verify,
)


def _session():
    return new_session("s_test")


def _utter(state, text):
    return next_epoch(state, text, at_ms=0)


def test_new_session_starts_at_epoch_zero_with_event():
    s = _session()
    assert s.epoch == 0
    assert s.facts == {}
    assert [e.type for e in s.events] == ["session_created"]


def test_utterance_bumps_epoch():
    s = _utter(_session(), "ten milligrams morphine")
    assert s.epoch == 1
    assert s.events[-1].type == "utterance"


def test_extraction_adds_heard_fact():
    s = _utter(_session(), "morphine ten milligrams")
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg")], epoch=1, at_ms=10)
    fact = s.fact("morphine_dose")
    assert fact.status is FactStatus.HEARD
    assert fact.value == "10 mg"
    assert fact.current.epoch == 1


def test_inferred_candidate_lands_as_inferred():
    s = _utter(_session(), "morphine ten")
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg", inferred=True)], epoch=1, at_ms=10)
    assert s.fact("morphine_dose").status is FactStatus.INFERRED


def test_state_is_immutable_between_transitions():
    s1 = _utter(_session(), "x")
    s2 = apply_extraction(s1, [Candidate("bp", "90/60")], epoch=1, at_ms=1)
    assert s1.fact("bp") is None
    assert s2.fact("bp") is not None


def test_correction_in_later_epoch_supersedes_old_value():
    s = _utter(_session(), "morphine ten")
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg")], epoch=1, at_ms=1)
    s = _utter(s, "wait it was five")
    s = apply_extraction(s, [Candidate("morphine_dose", "5 mg")], epoch=2, at_ms=2)
    fact = s.fact("morphine_dose")
    assert fact.status is FactStatus.CORRECTED
    assert fact.value == "5 mg"
    assert [v.status for v in fact.history] == [FactStatus.SUPERSEDED]
    assert fact.history[0].value == "10 mg"
    assert s.events[-1].type == "fact_corrected"


def test_correction_of_verified_value_requires_reverification():
    s = _utter(_session(), "allergy none")
    s = apply_extraction(s, [Candidate("allergy", "none")], epoch=1, at_ms=1)
    s = verify(s, "allergy", at_ms=2)
    s = _utter(s, "actually penicillin")
    s = apply_extraction(s, [Candidate("allergy", "penicillin")], epoch=2, at_ms=3)
    fact = s.fact("allergy")
    assert fact.status is FactStatus.CORRECTED
    assert relayable(s) == ()


def test_same_value_restated_keeps_status():
    s = _utter(_session(), "bp ninety over sixty")
    s = apply_extraction(s, [Candidate("bp", "90/60")], epoch=1, at_ms=1)
    s = verify(s, "bp", at_ms=2)
    s = _utter(s, "bp is 90/60")
    s = apply_extraction(s, [Candidate("bp", "90/60")], epoch=2, at_ms=3)
    assert s.fact("bp").status is FactStatus.VERIFIED
    assert s.events[-1].type == "fact_restated"


def test_equivalent_units_are_same_value():
    s = _utter(_session(), "x")
    s = apply_extraction(s, [Candidate("morphine_dose", "10 milligrams")], epoch=1, at_ms=1)
    s = _utter(s, "y")
    s = apply_extraction(s, [Candidate("morphine_dose", "10mg")], epoch=2, at_ms=2)
    assert s.fact("morphine_dose").status is FactStatus.HEARD


def test_two_values_in_same_epoch_conflict():
    s = _utter(_session(), "morphine ten, no five")
    s = apply_extraction(
        s, [Candidate("morphine_dose", "10 mg"), Candidate("morphine_dose", "5 mg")], epoch=1, at_ms=1
    )
    fact = s.fact("morphine_dose")
    assert fact.status is FactStatus.CONFLICTED
    assert [v.value for v in fact.conflict] == ["5 mg"]
    with pytest.raises(TransitionError):
        verify(s, "morphine_dose", at_ms=2)


def test_resolve_conflict_verifies_chosen_value_and_supersedes_rest():
    s = _utter(_session(), "x")
    s = apply_extraction(
        s, [Candidate("morphine_dose", "10 mg"), Candidate("morphine_dose", "5 mg")], epoch=1, at_ms=1
    )
    s = resolve_conflict(s, "morphine_dose", "5 mg", at_ms=2)
    fact = s.fact("morphine_dose")
    assert fact.status is FactStatus.VERIFIED
    assert fact.value == "5 mg"
    assert fact.conflict == ()
    assert [v.value for v in fact.history] == ["10 mg"]
    assert fact.history[0].status is FactStatus.SUPERSEDED


def test_resolve_with_unknown_value_is_rejected():
    s = _utter(_session(), "x")
    s = apply_extraction(
        s, [Candidate("morphine_dose", "10 mg"), Candidate("morphine_dose", "5 mg")], epoch=1, at_ms=1
    )
    with pytest.raises(TransitionError):
        resolve_conflict(s, "morphine_dose", "2 mg", at_ms=2)


def test_verify_moves_heard_to_verified_and_relay_gate_opens():
    s = _utter(_session(), "x")
    s = apply_extraction(s, [Candidate("allergy", "penicillin"), Candidate("bp", "90/60")], epoch=1, at_ms=1)
    assert relayable(s) == ()
    s = verify(s, "allergy", at_ms=2)
    assert [f.field for f in relayable(s)] == ["allergy"]


def test_verify_unknown_field_raises():
    with pytest.raises(TransitionError):
        verify(_session(), "nope", at_ms=1)


def test_provider_change_logs_once():
    s = set_provider(_session(), "fallback", at_ms=5, reason="rime unreachable")
    assert s.provider == "fallback"
    again = set_provider(s, "fallback", at_ms=6)
    assert again is s
