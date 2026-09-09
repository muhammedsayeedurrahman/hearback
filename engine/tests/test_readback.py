from engine.models import Candidate, FactStatus
from engine.readback import (
    acknowledgement,
    conflict_prompt,
    confirm_prompt,
    label,
    reconciliation,
    spoken_value,
    verified_line,
)
from engine.state import apply_extraction, new_session, next_epoch


def _fact(field, value, more=()):
    s = next_epoch(new_session("s"), "x", at_ms=0)
    s = apply_extraction(s, [Candidate(field, value)] + [Candidate(field, v) for v in more], epoch=1, at_ms=1)
    return s.fact(field)


def test_label_reads_fields_the_way_a_clinician_says_them():
    assert label("bp") == "blood pressure"
    assert label("spo2") == "oxygen saturation"
    assert label("time_of_incident") == "time of incident"
    assert label("morphine_dose") == "morphine"
    assert label("morphine_drug_time") == "time of morphine"
    assert label("mechanism") == "mechanism"


def test_spoken_value_states_the_number_twice():
    assert spoken_value("morphine_dose", "10 mg") == "[10] milligrams, spell(10) milligrams"
    assert spoken_value("spo2", "94%") == "[94] percent, spell(94) percent"


def test_spoken_value_speaks_blood_pressure_as_a_pair():
    assert spoken_value("bp", "90/60") == "[90] over [60], spell(90) over spell(60)"


def test_spoken_value_spells_look_alike_drug_names_only():
    assert spoken_value("allergy", "morphine") == "morphine, spell(morphine)"
    assert spoken_value("allergy", "penicillin") == "penicillin"


def test_confirm_prompt_spells_the_drug_and_slows_the_number():
    r = confirm_prompt(_fact("morphine_dose", "10 mg"))
    assert r.text == "Confirming. morphine, spell(morphine), [10] milligrams, spell(10) milligrams. Say yes to confirm."
    assert r.inline_speed_alpha == "0.8"
    assert r.critical is True


def test_confirm_prompt_leaves_unambiguous_drug_names_unspelled():
    r = confirm_prompt(_fact("paracetamol_dose", "1 g"))
    assert "spell(paracetamol)" not in r.text
    assert "[1] grams, spell(1) grams" in r.text


def test_acknowledgement_is_plain_for_non_critical_fields():
    r = acknowledgement(_fact("mechanism", "fall from height"))
    assert r.text == "Mechanism noted as fall from height."
    assert r.inline_speed_alpha is None
    assert r.critical is False


def test_verified_line_closes_the_loop():
    r = verified_line(_fact("allergy", "penicillin"))
    assert r.text == "Allergy, penicillin, verified."
    assert r.critical is True


def test_reconciliation_only_after_a_correction():
    assert reconciliation(_fact("bp", "90/60")) is None


def test_reconciliation_falls_back_to_the_old_value_when_nothing_was_delivered():
    s = next_epoch(new_session("s"), "morphine ten", at_ms=0)
    s = apply_extraction(s, [Candidate("morphine_dose", "10 mg")], epoch=1, at_ms=1)
    s = next_epoch(s, "make it five", at_ms=2)
    s = apply_extraction(s, [Candidate("morphine_dose", "5 mg")], epoch=2, at_ms=3)
    r = reconciliation(s.fact("morphine_dose"))
    assert r.text == "I had said 10 milligrams. You're now saying 5 milligrams. Use 5 milligrams as final?"


def test_conflict_prompt_offers_both_values():
    fact = _fact("morphine_dose", "10 mg", more=("5 mg",))
    assert fact.status is FactStatus.CONFLICTED
    r = conflict_prompt(fact)
    assert r.text == "I heard two values for morphine: 10 milligrams or 5 milligrams. Which one is right?"
    assert conflict_prompt(_fact("bp", "90/60")) is None


# --- identifiers and initialisms ------------------------------------------------------


def test_a_code_is_spelled_character_by_character():
    fact = _fact("mrn", "A472913")
    line = acknowledgement(fact)
    assert "spell(A472913)" in line.text
    assert "A 4 7 2 9 1 3" in line.plain


def test_the_plain_form_of_a_code_carries_no_markup():
    line = acknowledgement(_fact("unit_code", "AMB14"))
    assert "spell(" not in line.plain
    assert "[" not in line.plain


def test_an_initialism_keeps_its_capitals_in_a_sentence():
    assert acknowledgement(_fact("gcs", "13")).text.startswith("G C S")
    assert acknowledgement(_fact("mrn", "A1")).text.startswith("M R N")


def test_a_name_is_never_spelled():
    line = acknowledgement(_fact("patient_name", "Priya Venkataraman"))
    assert line.text == line.plain == "Patient name noted as Priya Venkataraman."
