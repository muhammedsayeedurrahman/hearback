"""The barge-in regression suite (F16).

Pins the demo scenario end to end and sweeps the interruption instant across the critical
read-back. The invariant under test is the product claim: whatever the agent says afterwards
about what the listener heard must match what was actually delivered.
"""

import json
from pathlib import Path

import pytest

from sim.barge_in import probe
from sim.replay import Scenario, Turn, replay

SCENARIO = Path("fixtures/scenario_morphine.json")
OFFSETS = json.loads(Path("fixtures/barge_in_offsets.json").read_text(encoding="utf-8"))["offsets_ms"]


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return Scenario.load(SCENARIO)


async def test_the_demo_scenario_ends_with_the_corrected_dose(scenario):
    result = await replay(scenario)
    assert result.facts["morphine_dose"]["value"] == "5 mg"
    assert result.facts["morphine_dose"]["status"] == "VERIFIED"
    assert "5 milligrams" in result.relay["plain"]
    assert "10 milligrams" not in result.relay["plain"]


async def test_nothing_is_withheld_once_the_handover_is_confirmed(scenario):
    result = await replay(scenario)
    assert result.relay["ready"] is True
    assert result.relay["withheld"] == []


async def test_the_superseded_dose_keeps_the_record_of_what_was_heard(scenario):
    result = await replay(scenario)
    history = result.facts["morphine_dose"]["history"]
    assert [v["value"] for v in history] == ["10 mg"]
    assert history[0]["status"] == "SUPERSEDED"
    assert history[0]["delivered"]["cutoff_word"] == "milligrams."
    assert history[0]["delivered"]["complete"] is False


async def test_the_reconciliation_quotes_the_words_that_were_delivered(scenario):
    result = await replay(scenario)
    cut = next(s for step in result.steps for s in step.spoken if s.cut_at_ms is not None)
    reconcile = next(s for step in result.steps for s in step.spoken if s.kind == "reconcile")
    assert cut.heard.rstrip(" .") in reconcile.text
    assert "Say yes to confirm" not in reconcile.text  # never claims words that never played


@pytest.mark.parametrize("offset_ms", OFFSETS)
async def test_every_barge_in_offset_is_reconciled_honestly(scenario, offset_ms):
    result = await probe(scenario, offset_ms)
    assert result.quoted_back, f"offset {offset_ms} ms quoted words that were not delivered"


async def test_a_critical_fact_never_crosses_the_relay_gate_unconfirmed(scenario):
    """Drop every confirmation. The ordinary facts still settle; the critical ones must not.

    An unchallenged acknowledgement settles a mechanism or a time of incident, because that is
    how a spoken handover works. A dose, a blood pressure, an oxygen saturation and an allergy
    need the paramedic to say yes, and without it they stay behind the gate.
    """
    turns = tuple(t for t in scenario.turns if not t.text.lower().startswith("yes"))
    result = await replay(Scenario(name="unconfirmed", description="", turns=turns))
    assert set(result.relay["withheld"]) >= {"bp", "spo2", "allergy", "morphine_dose"}
    assert result.relay["fields"] == ["age", "time_of_incident", "mechanism", "gcs"]
    for leaked in ("penicillin", "90 over 60", "91 percent", "milligrams"):
        assert leaked not in result.relay["plain"]


async def test_a_stale_extraction_cannot_resurrect_a_corrected_dose():
    """The paramedic corrects the dose while the first extraction is still in flight."""
    turns = (
        Turn(text="We gave morphine ten milligrams."),
        Turn(text="Wait, that was morphine five milligrams.", barge_in_at_ms=1300),
    )
    result = await replay(Scenario(name="race", description="", turns=turns))
    assert result.facts["morphine_dose"]["value"] == "5 mg"
