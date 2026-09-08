from engine.dialogue import awaiting_confirmation, is_affirmation, is_negation, next_line
from engine.ledger import WordTiming, cut
from engine.models import Candidate
from engine.state import apply_extraction, new_session, next_epoch, record_delivery, verify

WORDS = (
    WordTiming("Confirming.", 0, 600),
    WordTiming("Morphine,", 700, 1300),
    WordTiming("ten", 1500, 1900),
    WordTiming("milligrams.", 1950, 2600),
)


def _heard(pairs, session="s"):
    state = next_epoch(new_session(session), "handover", at_ms=0)
    return apply_extraction(state, [Candidate(f, v) for f, v in pairs], epoch=1, at_ms=1)


def test_silence_is_a_valid_next_move():
    assert next_line(new_session("s")) is None


def test_a_critical_fact_is_read_back_before_anything_is_acknowledged():
    line = next_line(_heard([("mechanism", "fall from height"), ("allergy", "penicillin")]))
    assert line.kind == "confirm" and line.fields == ("allergy",)
    assert line.text.startswith("Confirming. allergy,")
    assert line.critical is True and line.inline_speed_alpha == "0.8"


def test_a_non_critical_fact_is_merely_noted():
    line = next_line(_heard([("mechanism", "fall from height")]))
    assert line.kind == "acknowledge" and line.critical is False
    assert line.text == "Mechanism noted as fall from height."


def test_a_conflict_outranks_a_readback():
    state = _heard([("allergy", "penicillin")])
    state = apply_extraction(
        state,
        [Candidate("morphine_dose", "10 mg"), Candidate("morphine_dose", "5 mg")],
        epoch=1,
        at_ms=2,
    )
    line = next_line(state)
    assert line.kind == "conflict" and line.fields == ("morphine_dose",)
    assert "Which one is right?" in line.text


def test_speaking_about_a_fact_stops_it_being_raised_again():
    state = _heard([("allergy", "penicillin")])
    first = next_line(state)
    state = record_delivery(state, "allergy", cut(WORDS, None), at_ms=10, speech_epoch=1)
    assert first.kind == "confirm"
    assert next_line(state) is None


def test_a_correction_that_cut_into_a_readback_is_reconciled_first():
    state = _heard([("morphine_dose", "10 mg")])
    state = record_delivery(state, "morphine_dose", cut(WORDS, 1840), at_ms=1850, speech_epoch=1)
    state = next_epoch(state, "wait, five", at_ms=1900)
    state = apply_extraction(state, [Candidate("morphine_dose", "5 mg")], epoch=2, at_ms=1950)
    line = next_line(state)
    assert line.kind == "reconcile"
    assert "Confirming. Morphine, ten" in line.text and "5 milligrams" in line.text


def test_a_correction_nobody_heard_is_simply_read_back():
    state = _heard([("morphine_dose", "10 mg")])
    state = next_epoch(state, "wait, five", at_ms=100)
    state = apply_extraction(state, [Candidate("morphine_dose", "5 mg")], epoch=2, at_ms=110)
    assert next_line(state).kind == "confirm"


def test_verified_facts_are_not_raised_again():
    state = _heard([("allergy", "penicillin")])
    state = verify(state, "allergy", at_ms=5)
    assert next_line(state) is None


def test_awaiting_confirmation_lists_what_a_yes_would_verify():
    state = _heard([("allergy", "penicillin"), ("mechanism", "fall from height")])
    assert awaiting_confirmation(state) == ()
    state = record_delivery(state, "allergy", cut(WORDS, None), at_ms=10, speech_epoch=1)
    assert awaiting_confirmation(state) == ("allergy",)
    state = verify(state, "allergy", at_ms=11)
    assert awaiting_confirmation(state) == ()


def test_affirmation_and_negation_are_told_apart():
    assert is_affirmation("yes, that's right")
    assert is_affirmation("haan")
    assert not is_affirmation("no, that's wrong")
    assert not is_affirmation("morphine ten milligrams")
    assert is_negation("no, wrong dose")
    assert not is_negation("yes")


def test_a_yes_that_carries_a_correction_is_not_a_bare_confirmation():
    assert is_affirmation("yes but it was five milligrams") is True
    assert is_affirmation("no, yes, sorry, five milligrams") is False
