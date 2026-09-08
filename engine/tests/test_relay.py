from engine.models import Candidate
from engine.relay import EMPTY_RELAY, build
from engine.state import apply_extraction, new_session, next_epoch, verify


def _session(pairs):
    s = next_epoch(new_session("s"), "handover", at_ms=0)
    return apply_extraction(s, [Candidate(f, v) for f, v in pairs], epoch=1, at_ms=1)


def _verify_all(state, fields):
    for i, f in enumerate(fields):
        state = verify(state, f, at_ms=10 + i)
    return state


def test_nothing_verified_means_nothing_to_relay():
    r = build(new_session("s"))
    assert r.text == EMPTY_RELAY
    assert r.facts == () and r.withheld == () and r.inline_speed_alpha is None


def test_unverified_facts_are_withheld_from_the_relay():
    r = build(_session([("bp", "90/60"), ("mechanism", "fall from height")]))
    assert r.text == EMPTY_RELAY
    assert set(r.withheld) == {"bp", "mechanism"}


def test_relay_orders_facts_atmist_ambo():
    s = _session([("allergy", "penicillin"), ("morphine_dose", "10 mg"), ("bp", "90/60"), ("age", "34")])
    s = _verify_all(s, ["allergy", "morphine_dose", "bp", "age"])
    r = build(s)
    assert [f.field for f in r.facts] == ["age", "bp", "morphine_dose", "allergy"]
    assert r.text.startswith("Verified handover. Age, 34.")
    assert r.withheld == ()


def test_critical_fields_are_spoken_the_ncc_merp_way():
    s = _session([("bp", "90/60"), ("mechanism", "fall from height")])
    s = _verify_all(s, ["bp", "mechanism"])
    text = build(s).text
    assert "Blood pressure, [90] over [60], spell(90) over spell(60)." in text
    assert "Mechanism, fall from height." in text


def test_relay_carries_the_slow_number_hint_and_slot_completeness():
    s = _verify_all(_session([("bp", "90/60"), ("age", "34")]), ["bp", "age"])
    r = build(s)
    assert r.inline_speed_alpha == "0.8"
    assert r.completeness["signs"] is True and r.completeness["age"] is True
    assert r.completeness["allergies"] is False
    assert set(r.completeness) == {
        "identity", "age", "time_of_incident", "mechanism", "injuries", "signs",
        "treatment", "allergies", "medications", "background", "other",
    }


def test_partly_verified_handover_relays_only_what_crossed_the_gate():
    s = _session([("allergy", "penicillin"), ("bp", "90/60")])
    s = verify(s, "allergy", at_ms=5)
    r = build(s)
    assert [f.field for f in r.facts] == ["allergy"]
    assert r.withheld == ("bp",)
    assert "90" not in r.text
