"""Runtime configuration. Secrets are read from the environment, never from source."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_EXTRACTION_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    extraction_model: str
    extractor: str  # auto | claude | rules
    livekit_url: str | None
    livekit_api_key: str | None
    livekit_api_secret: str | None
    tool_delay_ms: int
    room_prefix: str
    cors_origins: tuple[str, ...]

    @property
    def can_mint_tokens(self) -> bool:
        return bool(self.livekit_api_key and self.livekit_api_secret and self.livekit_url)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _str_env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _origins() -> tuple[str, ...]:
    raw = _str_env("HEARBACK_CORS_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000"
    return tuple(o.strip() for o in raw.split(",") if o.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        anthropic_api_key=_str_env("ANTHROPIC_API_KEY"),
        extraction_model=_str_env("HEARBACK_EXTRACTION_MODEL") or DEFAULT_EXTRACTION_MODEL,
        extractor=(_str_env("HEARBACK_EXTRACTOR") or "auto").lower(),
        livekit_url=_str_env("LIVEKIT_URL"),
        livekit_api_key=_str_env("LIVEKIT_API_KEY"),
        livekit_api_secret=_str_env("LIVEKIT_API_SECRET"),
        tool_delay_ms=_int_env("TOOL_DELAY_MS", 0),
        room_prefix=_str_env("HEARBACK_ROOM_PREFIX") or "hearback",
        cors_origins=_origins(),
    )
