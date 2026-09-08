import pytest

from api import rules
from api.extraction import ClaudeExtractor, RuleExtractor, _parse, build_extractor
from api.settings import Settings


def _values(candidates):
    return {(c.field, c.value) for c in candidates}


def _settings(**overrides) -> Settings:
    base = dict(
        anthropic_api_key=None,
        extraction_model="none",
        extractor="auto",
        livekit_url=None,
        livekit_api_key=None,
        livekit_api_secret=None,
        tool_delay_ms=0,
        room_prefix="test",
        cors_origins=(),
    )
    return Settings(**{**base, **overrides})


def test_rules_read_a_whole_atmist_utterance():
    text = "34 year old male, fall from height at 14:05, GCS 13, BP ninety over sixty, sats 91 percent"
    assert _values(rules.extract(text)) == {
        ("age", "34"),
        ("mechanism", "fall from height"),
        ("time_of_incident", "14:05"),
        ("gcs", "13"),
        ("bp", "90/60"),
        ("spo2", "91%"),
    }


def test_rules_read_doses_in_either_word_order():
    assert _values(rules.extract("morphine ten milligrams IV")) == {("morphine_dose", "10 mg")}
    assert _values(rules.extract("gave 500 mg paracetamol")) == {("paracetamol_dose", "500 mg")}


def test_rules_do_not_invent_a_drug_out_of_an_ordinary_word():
    assert rules.extract("we gave another 5 mg") == ()
    assert rules.extract("total dose 10 mg") == ()


def test_rules_keep_two_values_for_one_field_so_the_engine_can_call_it_a_conflict():
    found = rules.extract("morphine ten milligrams, no wait, morphine five milligrams")
    assert [c.value for c in found] == ["10 mg", "5 mg"]


def test_rules_collapse_a_plain_repetition():
    found = rules.extract("morphine 10 mg, that is morphine ten milligrams")
    assert [c.value for c in found] == ["10 mg"]


def test_rules_hear_the_absence_of_an_allergy():
    assert _values(rules.extract("no known allergies")) == {("allergy", "none")}
    assert _values(rules.extract("allergic to penicillin")) == {("allergy", "penicillin")}


async def test_rule_extractor_reports_its_source():
    result = await RuleExtractor().extract("bp ninety over sixty")
    assert result.source == "rules" and result.error is None
    assert _values(result.candidates) == {("bp", "90/60")}


def test_parse_accepts_fenced_and_bare_json():
    fenced = '```json\n{"facts": [{"field": "bp", "value": "90/60"}]}\n```'
    assert _values(_parse(fenced)) == {("bp", "90/60")}
    assert _values(_parse('[{"field": "hr", "value": "122"}]')) == {("hr", "122")}


def test_parse_drops_rows_that_are_not_facts():
    payload = '{"facts": [{"field": "bp"}, {"value": "90/60"}, "nonsense", {"field": "HR ", "value": "122"}]}'
    assert _values(_parse(payload)) == {("hr", "122")}


def test_parse_rejects_a_payload_with_no_fact_list():
    with pytest.raises(ValueError):
        _parse('{"facts": "none"}')


async def test_claude_extractor_falls_back_to_rules_rather_than_going_silent():
    extractor = ClaudeExtractor(api_key="not-a-real-key", model="none")

    class _Failing:
        async def create(self, **_kwargs):
            raise RuntimeError("upstream unavailable")

    extractor._client.messages = _Failing()
    result = await extractor.extract("morphine ten milligrams")
    assert result.source == "rules-fallback"
    assert result.error == "upstream unavailable"
    assert _values(result.candidates) == {("morphine_dose", "10 mg")}


def test_build_extractor_stays_offline_without_a_key():
    assert build_extractor(_settings()).name == "rules"
    assert build_extractor(_settings(extractor="rules", anthropic_api_key="k")).name == "rules"


def test_build_extractor_refuses_to_pretend_when_claude_is_demanded():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_extractor(_settings(extractor="claude"))
