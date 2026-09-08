"""Async client for the Hearback sidecar.

The agent holds no truth state of its own. It reports what was said, what was synthesised and
what was heard, and reads back the decisions the engine makes. Anything else would be a second
copy of the state, drifting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class NextLine:
    """The sentence the engine wants spoken, and the facts it covers."""

    kind: str
    text: str
    plain: str
    fields: tuple[str, ...]
    inline_speed_alpha: str | None
    critical: bool

    @staticmethod
    def from_dict(raw: dict[str, Any] | None) -> "NextLine | None":
        if not raw:
            return None
        return NextLine(
            kind=raw["kind"],
            text=raw["text"],
            plain=raw.get("plain") or raw["text"],
            fields=tuple(raw["fields"]),
            inline_speed_alpha=raw.get("inline_speed_alpha"),
            critical=bool(raw.get("critical")),
        )


@dataclass(frozen=True)
class ExtractionOutcome:
    """What the sidecar did with an extraction request, including the fence's verdict."""

    applied: bool
    requested_epoch: int
    current_epoch: int
    source: str
    facts: dict[str, Any]
    next_line: NextLine | None = None
    awaiting_confirmation: tuple[str, ...] = ()
    error: str | None = None


class HearbackClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        session_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._owns_client = client is None
        self.session_id = session_id or ""

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "HearbackClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def create_session(self, session_id: str | None = None, identity: str = "paramedic") -> dict[str, Any]:
        body = await self._post("/session", {"session_id": session_id, "identity": identity})
        self.session_id = body["session_id"]
        return body

    async def utterance(self, text: str, speaker: str = "sender", at_ms: int | None = None) -> int:
        """Report a finished user turn. The returned epoch stamps everything produced for it."""
        body = await self._post("/utterance", self._with_session(text=text, speaker=speaker, at_ms=at_ms))
        return int(body["epoch"])

    async def extract(self, text: str, epoch: int, at_ms: int | None = None) -> ExtractionOutcome:
        body = await self._post("/extract", self._with_session(text=text, epoch=epoch, at_ms=at_ms))
        return ExtractionOutcome(
            applied=bool(body["applied"]),
            requested_epoch=int(body["requested_epoch"]),
            current_epoch=int(body["state"]["epoch"]),
            source=str(body["source"]),
            facts=body["state"]["facts"],
            next_line=NextLine.from_dict(body.get("next_line")),
            awaiting_confirmation=tuple(body.get("awaiting_confirmation", ())),
            error=body.get("error"),
        )

    async def next_line(self) -> NextLine | None:
        """Ask the engine what to say now. The agent never composes clinical sentences itself."""
        response = await self._client.get("/state", params={"session_id": self.session_id})
        response.raise_for_status()
        return NextLine.from_dict(response.json().get("next_line"))

    async def awaiting_confirmation(self) -> tuple[str, ...]:
        """Fields already read back and still unverified: what a bare "yes" would confirm."""
        response = await self._client.get("/state", params={"session_id": self.session_id})
        response.raise_for_status()
        return tuple(response.json().get("awaiting_confirmation", ()))

    async def verify(self, field: str, by: str = "sender") -> dict[str, Any]:
        return await self._post("/verify", self._with_session(field=field, by=by))

    async def resolve(self, field: str, value: str, by: str = "sender") -> dict[str, Any]:
        return await self._post("/resolve", self._with_session(field=field, value=value, by=by))

    async def delivery(self, field: str, speech_epoch: int, **timing: Any) -> dict[str, Any]:
        return await self._post("/delivery", self._with_session(field=field, speech_epoch=speech_epoch, **timing))

    async def relay(self, lang: str = "en") -> dict[str, Any]:
        body = await self._post("/relay", self._with_session(lang=lang))
        return body["relay"]

    async def set_provider(self, provider: str, reason: str = "") -> dict[str, Any]:
        return await self._post("/provider", self._with_session(provider=provider, reason=reason))

    async def set_tool_delay(self, delay_ms: int, target: str = "tool") -> dict[str, Any]:
        return await self._post("/stress/tool-delay", self._with_session(delay_ms=delay_ms, target=target))

    async def state(self) -> dict[str, Any]:
        response = await self._client.get("/state", params={"session_id": self.session_id})
        response.raise_for_status()
        return response.json()["state"]

    def _with_session(self, **fields: Any) -> dict[str, Any]:
        if not self.session_id:
            raise RuntimeError("no session: call create_session() first")
        return {"session_id": self.session_id, **{k: v for k, v in fields.items() if v is not None}}

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(path, json={k: v for k, v in body.items() if v is not None})
        response.raise_for_status()
        return response.json()
