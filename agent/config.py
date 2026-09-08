"""Voice-stack configuration.

The Rime settings here are the ones the README documents verbatim: model `coda`, PCM at 16 kHz
over ws3, one speaker per language. Two details are easy to get wrong and are handled here rather
than in the wiring: the LiveKit plugin appends `/ws3` to the base URL itself, and omitting
`modelId` silently serves Mist v3, which has no Hindi.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

RIME_WS_BASE = "wss://users-ws.rime.ai"
RIME_CATALOG_URL = "https://users.rime.ai/data/voices/all-v2.json"
DEFAULT_MODEL = "coda"
DEFAULT_SAMPLE_RATE = 16000

# Coda reads a bracketed token at inlineSpeedAlpha. Below 1.0 is slower; numbers get 0.8.
DEFAULT_SPEED_ALPHA = 0.95
NUMBER_SPEED_ALPHA = 0.8

LANG_CODES = {"en": "eng", "hi": "hin"}


class ConfigError(RuntimeError):
    """Raised when the voice stack is asked to start without what it needs."""


@dataclass(frozen=True)
class RimeConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    speaker_en: str = "lyra"
    speaker_hi: str = "nadi"
    sample_rate: int = DEFAULT_SAMPLE_RATE
    speed_alpha: float = DEFAULT_SPEED_ALPHA
    inline_speed_alpha: float = NUMBER_SPEED_ALPHA
    ws_base_url: str = RIME_WS_BASE
    catalog_url: str = RIME_CATALOG_URL

    def speaker_for(self, lang: str) -> str:
        return self.speaker_hi if lang == "hi" else self.speaker_en

    def lang_code(self, lang: str) -> str:
        return LANG_CODES.get(lang, "eng")


@dataclass(frozen=True)
class AgentConfig:
    rime: RimeConfig
    deepgram_api_key: str | None
    stt_model: str
    api_base_url: str
    lang: str

    @property
    def can_transcribe(self) -> bool:
        return bool(self.deepgram_api_key)


def normalise_ws_base(url: str) -> str:
    """The plugin builds `<base>/ws3`, so a configured `.../ws3` would double up."""
    trimmed = url.strip().rstrip("/")
    if trimmed.endswith("/ws3"):
        trimmed = trimmed[: -len("/ws3")]
    return trimmed or RIME_WS_BASE


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def load_rime_config() -> RimeConfig:
    api_key = _env("RIME_API_KEY")
    if not api_key:
        raise ConfigError("RIME_API_KEY is not set; the voice agent cannot speak")
    return RimeConfig(
        api_key=api_key,
        model=_env("RIME_MODEL_ID", DEFAULT_MODEL),
        speaker_en=_env("RIME_SPEAKER_EN", "lyra"),
        speaker_hi=_env("RIME_SPEAKER_HI", "nadi"),
        sample_rate=int(_env("RIME_SAMPLE_RATE", str(DEFAULT_SAMPLE_RATE))),
        ws_base_url=normalise_ws_base(_env("RIME_WS_URL", RIME_WS_BASE)),
        catalog_url=_env("RIME_CATALOG_URL", RIME_CATALOG_URL),
    )


def load_agent_config() -> AgentConfig:
    return AgentConfig(
        rime=load_rime_config(),
        deepgram_api_key=_env("DEEPGRAM_API_KEY") or None,
        stt_model=_env("DEEPGRAM_MODEL", "nova-3"),
        api_base_url=_env("HEARBACK_API_URL", "http://127.0.0.1:8000"),
        lang=_env("RIME_LANG", "en"),
    )


def check_catalog(catalog: list[dict], config: RimeConfig, lang: str) -> tuple[bool, str]:
    """Preflight a speaker against the live voice catalog before the demo, not during it."""
    speaker = config.speaker_for(lang)
    for voice in catalog:
        if voice.get("name") != speaker:
            continue
        models = voice.get("models") or []
        if models and config.model not in models:
            return False, f"speaker {speaker!r} exists but not for model {config.model!r}"
        languages = voice.get("languages") or voice.get("lang") or []
        wanted = config.lang_code(lang)
        if languages and wanted not in languages:
            return False, f"speaker {speaker!r} does not carry language {wanted!r}"
        return True, f"speaker {speaker!r} available for {config.model} / {wanted}"
    return False, f"speaker {speaker!r} is not in the catalog"
