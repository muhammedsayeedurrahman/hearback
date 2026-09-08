from agent.config import (
    RIME_WS_BASE,
    RimeConfig,
    check_catalog,
    normalise_ws_base,
)

CONFIG = RimeConfig(api_key="k")


def test_ws_base_is_normalised_because_the_plugin_appends_ws3():
    assert normalise_ws_base("wss://users-ws.rime.ai/ws3") == "wss://users-ws.rime.ai"
    assert normalise_ws_base("wss://users-ws.rime.ai/") == "wss://users-ws.rime.ai"
    assert normalise_ws_base("  ") == RIME_WS_BASE


def test_speaker_and_language_follow_the_relay_language():
    assert CONFIG.speaker_for("en") == "lyra" and CONFIG.lang_code("en") == "eng"
    assert CONFIG.speaker_for("hi") == "nadi" and CONFIG.lang_code("hi") == "hin"
    assert CONFIG.lang_code("xx") == "eng"


def test_catalog_preflight_accepts_a_speaker_that_carries_the_model_and_language():
    catalog = [{"name": "lyra", "models": ["coda"], "languages": ["eng", "hin"]}]
    ok, message = check_catalog(catalog, CONFIG, "en")
    assert ok and "available" in message


def test_catalog_preflight_names_what_is_wrong():
    missing = check_catalog([{"name": "astra", "models": ["coda"]}], CONFIG, "en")
    assert missing == (False, "speaker 'lyra' is not in the catalog")

    wrong_model = check_catalog([{"name": "lyra", "models": ["mistv2"]}], CONFIG, "en")
    assert wrong_model[0] is False and "not for model 'coda'" in wrong_model[1]

    wrong_lang = check_catalog([{"name": "nadi", "models": ["coda"], "languages": ["eng"]}], CONFIG, "hi")
    assert wrong_lang[0] is False and "does not carry language 'hin'" in wrong_lang[1]


def test_catalog_entry_without_metadata_is_accepted_rather_than_guessed_at():
    ok, _ = check_catalog([{"name": "lyra"}], CONFIG, "en")
    assert ok is True
