"""The agent's HTTP contract, exercised against a real sidecar running in-process."""

import pytest

from agent.tools import accept_result, allergy_check

WORDS = [
    {"word": "Confirming.", "start_ms": 0, "end_ms": 600},
    {"word": "Morphine,", "start_ms": 700, "end_ms": 1300},
    {"word": "ten", "start_ms": 1500, "end_ms": 1900},
    {"word": "milligrams.", "start_ms": 1950, "end_ms": 2600},
]


async def test_client_needs_a_session_before_it_reports_anything():
    from agent.client import HearbackClient

    with pytest.raises(RuntimeError, match="no session"):
        await HearbackClient().utterance("morphine ten milligrams")


async def test_an_utterance_opens_an_epoch_and_extraction_lands_under_it(hearback):
    epoch = await hearback.utterance("we gave morphine ten milligrams")
    outcome = await hearback.extract("we gave morphine ten milligrams", epoch=epoch)
    assert outcome.applied is True and outcome.source == "rules"
    assert outcome.facts["morphine_dose"]["value"] == "10 mg"


async def test_the_fence_holds_across_the_wire(hearback):
    first = await hearback.utterance("morphine ten milligrams")
    await hearback.utterance("wait, five milligrams of morphine")
    outcome = await hearback.extract("morphine ten milligrams", epoch=first)
    assert outcome.applied is False
    assert outcome.requested_epoch == first and outcome.current_epoch == 2
    assert outcome.facts == {}


async def test_the_full_barge_in_scenario_end_to_end(hearback):
    """Ten milligrams spoken, cut off mid-word, corrected to five, relayed as five."""
    first = await hearback.utterance("we gave morphine ten milligrams")
    await hearback.extract("we gave morphine ten milligrams", epoch=first)

    second = await hearback.utterance("wait, that was morphine five milligrams")
    await hearback.extract("wait, that was morphine five milligrams", epoch=second)
    await hearback.delivery(
        field="morphine_dose", speech_epoch=first, words=WORDS, interrupted_at_ms=1840
    )

    state = await hearback.state()
    fact = state["facts"]["morphine_dose"]
    assert fact["status"] == "CORRECTED" and fact["value"] == "5 mg"
    assert fact["history"][0]["delivered"]["cutoff_word"] == "ten"

    withheld = await hearback.relay()
    assert withheld["ready"] is False and withheld["withheld"] == ["morphine_dose"]

    await hearback.verify("morphine_dose")
    relay = await hearback.relay()
    assert relay["ready"] is True
    assert "spell(5) milligrams" in relay["text"] and "10" not in relay["text"]


async def test_conflicts_are_resolved_through_the_client(hearback):
    text = "morphine ten milligrams, no wait, morphine five milligrams"
    epoch = await hearback.utterance(text)
    outcome = await hearback.extract(text, epoch=epoch)
    assert outcome.facts["morphine_dose"]["status"] == "CONFLICTED"
    body = await hearback.resolve("morphine_dose", "5 mg")
    assert body["state"]["facts"]["morphine_dose"]["status"] == "VERIFIED"


async def test_provider_fallback_is_reported_not_hidden(hearback):
    body = await hearback.set_provider("fallback", reason="rime unreachable")
    assert body["state"]["provider"] == "fallback"


async def test_cross_check_flags_a_recorded_allergy(hearback):
    epoch = await hearback.utterance("allergic to morphine")
    await hearback.extract("allergic to morphine", epoch=epoch)
    result = await allergy_check(hearback, drug="morphine", epoch=epoch)
    assert result.matches_recorded_allergy is True
    assert result.look_alike == "hydromorphone"
    assert "matches the recorded allergy" in result.summary


async def test_cross_check_stays_quiet_when_nothing_matches(hearback):
    epoch = await hearback.utterance("allergic to penicillin")
    await hearback.extract("allergic to penicillin", epoch=epoch)
    result = await allergy_check(hearback, drug="paracetamol", epoch=epoch)
    assert result.matches_recorded_allergy is False and result.look_alike is None
    assert result.summary == "No recorded allergy conflict for paracetamol."


async def test_a_slow_cross_check_answering_a_superseded_epoch_is_dropped(hearback):
    epoch = await hearback.utterance("allergic to morphine")
    await hearback.extract("allergic to morphine", epoch=epoch)
    result = await allergy_check(hearback, drug="morphine", epoch=epoch, delay_ms=10)

    later = await hearback.utterance("sorry, no known allergies")
    assert accept_result(result, current_epoch=later) is False
    assert accept_result(result, current_epoch=epoch) is True


async def test_stress_delay_is_set_through_the_client(hearback):
    body = await hearback.set_tool_delay(3000)
    assert body["stress"]["tool_delay_ms"] == 3000
