import pytest
from fastapi.testclient import TestClient

from api.extraction import RuleExtractor
from api.main import create_app
from api.settings import Settings

WORDS = [
    {"word": "Confirming.", "start_ms": 0, "end_ms": 600},
    {"word": "Morphine,", "start_ms": 700, "end_ms": 1300},
    {"word": "ten", "start_ms": 1500, "end_ms": 1900},
    {"word": "milligrams.", "start_ms": 1950, "end_ms": 2600},
]


def _settings() -> Settings:
    """Offline settings: no keys, deterministic extraction, no network in CI."""
    return Settings(
        anthropic_api_key=None,
        extraction_model="none",
        extractor="rules",
        livekit_url=None,
        livekit_api_key=None,
        livekit_api_secret=None,
        tool_delay_ms=0,
        room_prefix="test",
        cors_origins=("http://localhost:3000",),
    )


@pytest.fixture
def client():
    with TestClient(create_app(extractor=RuleExtractor(), settings=_settings())) as c:
        yield c


def _session(client, session_id="s1") -> str:
    return client.post("/session", json={"session_id": session_id}).json()["session_id"]


def _say(client, sid, text) -> int:
    return client.post("/utterance", json={"session_id": sid, "text": text}).json()["epoch"]


def _extract(client, sid, text, epoch) -> dict:
    return client.post("/extract", json={"session_id": sid, "text": text, "epoch": epoch}).json()


def test_health_reports_the_active_extractor(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "extractor": "rules", "livekit_configured": False}


def test_session_starts_empty_and_says_why_there_is_no_token(client):
    body = client.post("/session", json={"session_id": "s1"}).json()
    assert body["state"]["epoch"] == 0 and body["state"]["facts"] == {}
    assert body["livekit"]["token"] is None
    assert "not configured" in body["livekit"]["reason"]
    assert body["livekit"]["room"] == "test-s1"


def test_session_creation_is_idempotent(client):
    sid = _session(client)
    _say(client, sid, "morphine ten milligrams")
    again = client.post("/session", json={"session_id": sid}).json()
    assert again["state"]["epoch"] == 1


def test_utterance_then_extract_lands_a_heard_fact(client):
    sid = _session(client)
    epoch = _say(client, sid, "we gave morphine ten milligrams")
    body = _extract(client, sid, "we gave morphine ten milligrams", epoch)
    assert body["applied"] is True and body["source"] == "rules"
    fact = body["state"]["facts"]["morphine_dose"]
    assert fact["value"] == "10 mg" and fact["status"] == "HEARD"


def test_extraction_for_a_superseded_epoch_is_dropped_over_http(client):
    sid = _session(client)
    first = _say(client, sid, "morphine ten milligrams")
    _say(client, sid, "wait, make that five milligrams of morphine")
    body = _extract(client, sid, "morphine ten milligrams", first)
    assert body["applied"] is False and body["requested_epoch"] == 1
    assert body["state"]["facts"] == {}


def test_extraction_from_the_future_is_rejected_as_an_upstream_bug(client):
    sid = _session(client)
    _say(client, sid, "morphine ten milligrams")
    response = client.post("/extract", json={"session_id": sid, "text": "morphine ten milligrams", "epoch": 9})
    assert response.status_code == 409
    assert "ahead of" in response.json()["detail"]


def test_verify_opens_the_relay_gate_and_withholds_the_rest(client):
    sid = _session(client)
    epoch = _say(client, sid, "allergic to penicillin, bp ninety over sixty")
    _extract(client, sid, "allergic to penicillin, bp ninety over sixty", epoch)
    assert client.post("/relay", json={"session_id": sid}).json()["relay"]["ready"] is False

    client.post("/verify", json={"session_id": sid, "field": "allergy"})
    relay = client.post("/relay", json={"session_id": sid}).json()["relay"]
    assert relay["ready"] is True
    assert relay["fields"] == ["allergy"] and relay["withheld"] == ["bp"]
    assert "penicillin" in relay["text"] and "90" not in relay["text"]
    assert relay["completeness"]["allergies"] is True


def test_conflicting_values_block_verification_until_resolved(client):
    sid = _session(client)
    text = "morphine ten milligrams, no wait, morphine five milligrams"
    epoch = _say(client, sid, text)
    body = _extract(client, sid, text, epoch)
    assert body["state"]["facts"]["morphine_dose"]["status"] == "CONFLICTED"

    blocked = client.post("/verify", json={"session_id": sid, "field": "morphine_dose"})
    assert blocked.status_code == 409

    resolved = client.post("/resolve", json={"session_id": sid, "field": "morphine_dose", "value": "5 mg"})
    fact = resolved.json()["state"]["facts"]["morphine_dose"]
    assert fact["status"] == "VERIFIED" and fact["value"] == "5 mg"


def test_resolving_with_a_value_nobody_said_is_refused(client):
    sid = _session(client)
    text = "morphine ten milligrams, no wait, morphine five milligrams"
    _extract(client, sid, text, _say(client, sid, text))
    response = client.post("/resolve", json={"session_id": sid, "field": "morphine_dose", "value": "2 mg"})
    assert response.status_code == 409


def test_delivery_records_the_word_the_listener_was_cut_off_at(client):
    sid = _session(client)
    epoch = _say(client, sid, "morphine ten milligrams")
    _extract(client, sid, "morphine ten milligrams", epoch)
    body = client.post(
        "/delivery",
        json={
            "session_id": sid,
            "field": "morphine_dose",
            "speech_epoch": epoch,
            "words": WORDS,
            "interrupted_at_ms": 1840,
        },
    ).json()
    assert body["delivered"]["cutoff_word"] == "ten"
    assert body["delivered"]["text_heard"] == "Confirming. Morphine, ten"
    assert body["delivered"]["complete"] is False
    assert body["state"]["facts"]["morphine_dose"]["delivered"]["cutoff_word"] == "ten"


def test_delivery_needs_a_timing_source(client):
    sid = _session(client)
    response = client.post("/delivery", json={"session_id": sid, "field": "bp", "speech_epoch": 0})
    assert response.status_code == 422


def test_stress_delay_is_recorded_per_session(client):
    sid = _session(client)
    body = client.post("/stress/tool-delay", json={"session_id": sid, "delay_ms": 3000}).json()
    assert body["stress"] == {"tool_delay_ms": 3000, "extract_delay_ms": 0}


def test_unknown_session_is_a_404_everywhere(client):
    assert client.get("/state", params={"session_id": "nope"}).status_code == 404
    assert client.post("/utterance", json={"session_id": "nope", "text": "hi"}).status_code == 404
    assert client.get("/events", params={"session_id": "nope"}).status_code == 404


def test_verifying_a_field_nobody_mentioned_is_a_409(client):
    sid = _session(client)
    assert client.post("/verify", json={"session_id": sid, "field": "allergy"}).status_code == 409


def test_provider_fallback_is_visible_in_the_state(client):
    sid = _session(client)
    body = client.post("/provider", json={"session_id": sid, "provider": "fallback", "reason": "rime timeout"}).json()
    assert body["state"]["provider"] == "fallback"


def test_event_stream_replays_the_handover_so_far(client):
    sid = _session(client)
    _say(client, sid, "morphine ten milligrams")
    seen: list[str] = []
    with client.stream("GET", "/events", params={"session_id": sid, "follow": False}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("event: "):
                seen.append(line.removeprefix("event: ").strip())
    assert seen == ["session_created", "utterance"]


def test_event_stream_can_resume_from_a_sequence_number(client):
    sid = _session(client)
    _say(client, sid, "morphine ten milligrams")
    seen: list[str] = []
    with client.stream("GET", "/events", params={"session_id": sid, "since": 1, "follow": False}) as response:
        for line in response.iter_lines():
            if line.startswith("event: "):
                seen.append(line.removeprefix("event: ").strip())
    assert seen == ["utterance"]


def test_utterance_reports_whether_the_turn_was_a_confirmation(client):
    session = client.post("/session", json={}).json()["session_id"]
    plain = client.post("/utterance", json={"session_id": session, "text": "BP is ninety over sixty."})
    assert plain.json()["confirmation"] == {"affirmation": False, "negation": False}

    yes = client.post("/utterance", json={"session_id": session, "text": "Yes, that's right."})
    assert yes.json()["confirmation"]["affirmation"] is True

    no = client.post("/utterance", json={"session_id": session, "text": "No, that's wrong."})
    assert no.json()["confirmation"] == {"affirmation": False, "negation": True}


def test_the_sidecar_does_not_verify_on_a_confirmation_by_itself(client):
    """Only the speaking client knows a 'yes' was spoken rather than typed, so it acts on it."""
    session = client.post("/session", json={}).json()["session_id"]
    epoch = client.post("/utterance", json={"session_id": session, "text": "We gave morphine ten milligrams."}).json()["state"]["epoch"]
    client.post("/extract", json={"session_id": session, "text": "We gave morphine ten milligrams.", "epoch": epoch})
    client.post("/utterance", json={"session_id": session, "text": "Yes."})
    state = client.get("/state", params={"session_id": session}).json()["state"]
    assert state["facts"]["morphine_dose"]["status"] != "VERIFIED"


def test_verify_refuses_a_confirmation_that_names_an_unheard_value(client):
    """The 'yes' says five; the agent read back ten. Nothing may cross the gate on that."""
    session = client.post("/session", json={}).json()["session_id"]
    epoch = client.post("/utterance", json={"session_id": session, "text": "We gave morphine ten milligrams."}).json()["state"]["epoch"]
    client.post("/extract", json={"session_id": session, "text": "We gave morphine ten milligrams.", "epoch": epoch})
    client.post("/delivery", json={
        "session_id": session,
        "field": "morphine_dose",
        "speech_epoch": epoch,
        "text": "Confirming. morphine, 10 milligrams. Say yes to confirm.",
        "duration_ms": 2500,
    })

    refused = client.post("/verify", json={
        "session_id": session, "field": "morphine_dose", "spoken": "Yes, five milligrams is correct."
    }).json()
    assert refused["verified"] is False
    assert "never read back" in refused["challenge"]
    assert refused["state"]["facts"]["morphine_dose"]["status"] != "VERIFIED"

    accepted = client.post("/verify", json={
        "session_id": session, "field": "morphine_dose", "spoken": "Yes, ten milligrams is correct."
    }).json()
    assert accepted["verified"] is True
    assert accepted["challenge"] is None
    assert accepted["state"]["facts"]["morphine_dose"]["status"] == "VERIFIED"
