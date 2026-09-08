"""Request and response shapes. Every boundary value is validated before it reaches the engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

FIELD_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class SessionRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    identity: str = Field(default="paramedic", max_length=64)


class UtteranceRequest(BaseModel):
    session_id: str = Field(max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    speaker: Literal["sender", "receiver", "agent"] = "sender"
    at_ms: int | None = Field(default=None, ge=0)


class ExtractRequest(BaseModel):
    session_id: str = Field(max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    epoch: int = Field(ge=0)
    at_ms: int | None = Field(default=None, ge=0)


class VerifyRequest(BaseModel):
    session_id: str = Field(max_length=64)
    field: str = Field(pattern=FIELD_PATTERN)
    by: Literal["sender", "receiver"] = "sender"
    at_ms: int | None = Field(default=None, ge=0)


class ResolveRequest(BaseModel):
    session_id: str = Field(max_length=64)
    field: str = Field(pattern=FIELD_PATTERN)
    value: str = Field(min_length=1, max_length=200)
    by: Literal["sender", "receiver"] = "sender"
    at_ms: int | None = Field(default=None, ge=0)


class WordTimingIn(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class DeliveryRequest(BaseModel):
    """What the listener actually heard of a spoken sentence, and where it was cut off."""

    session_id: str = Field(max_length=64)
    field: str = Field(pattern=FIELD_PATTERN)
    speech_epoch: int = Field(ge=0)
    words: list[WordTimingIn] | None = None
    text: str | None = Field(default=None, max_length=4000)
    heard_text: str | None = Field(default=None, max_length=4000)
    interrupted_at_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    at_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _needs_a_timing_source(self) -> "DeliveryRequest":
        if self.words or (self.text and self.heard_text is not None) or (self.text and self.duration_ms):
            return self
        raise ValueError("supply words, or text with heard_text, or text with duration_ms")


class RelayRequest(BaseModel):
    session_id: str = Field(max_length=64)
    lang: Literal["en", "hi"] = "en"
    at_ms: int | None = Field(default=None, ge=0)


class ToolDelayRequest(BaseModel):
    session_id: str = Field(max_length=64)
    delay_ms: int = Field(ge=0, le=30000)
    target: Literal["tool", "extract"] = "tool"


class ProviderRequest(BaseModel):
    session_id: str = Field(max_length=64)
    provider: str = Field(min_length=1, max_length=40)
    reason: str = Field(default="", max_length=200)
    at_ms: int | None = Field(default=None, ge=0)


class StateResponse(BaseModel):
    state: dict[str, Any]
    stress: dict[str, int]
