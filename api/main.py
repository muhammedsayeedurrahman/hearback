"""Hearback REST + SSE sidecar.

Every route is a thin shell: validate at the boundary, run one engine transition under the
session lock, return the new snapshot. No clinical decision is taken here — the engine owns the
truth state and the relay gate, and this file owns nothing but transport.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from api import livekit_tokens, sse
from api.extraction import Extractor, build_extractor
from api.schemas import (
    DeliveryRequest,
    ExtractRequest,
    ProviderRequest,
    RelayRequest,
    ResolveRequest,
    SessionRequest,
    ToolDelayRequest,
    UtteranceRequest,
    VerifyRequest,
)
from api.settings import Settings, get_settings
from api.store import SessionNotFound, SessionStore
from engine.dialogue import awaiting_confirmation, next_line
from engine.ledger import WordTiming, cut, cut_from_text, estimate_words
from engine.models import TruthState
from engine.relay import build as build_relay
from engine.state import (
    TransitionError,
    apply_extraction,
    next_epoch,
    record_delivery,
    resolve_conflict,
    set_provider,
    verify,
    verify_unchallenged,
)

logger = logging.getLogger(__name__)


def create_app(
    store: SessionStore | None = None,
    extractor: Extractor | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or SessionStore()
    extractor = extractor or build_extractor(settings)

    app = FastAPI(title="Hearback", version="0.1.0", description="Verified clinical handover relay")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.store = store
    app.state.extractor = extractor
    app.state.settings = settings

    @app.exception_handler(SessionNotFound)
    async def _unknown_session(_request: Request, exc: SessionNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"unknown session {exc.args[0]!r}"})

    @app.exception_handler(TransitionError)
    async def _bad_transition(_request: Request, exc: TransitionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    return _register_routes(app)


def _store(request: Request) -> SessionStore:
    return request.app.state.store


def _extractor(request: Request) -> Extractor:
    return request.app.state.extractor


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _snapshot(store: SessionStore, session_id: str, state: TruthState, /, **extra: Any) -> dict[str, Any]:
    """Positional-only so a route can add its own `session_id` key to the payload."""
    stress = store.stress(session_id)
    line = next_line(state)
    return {
        "state": state.to_dict(),
        "stress": {"tool_delay_ms": stress.tool_delay_ms, "extract_delay_ms": stress.extract_delay_ms},
        "next_line": line.to_dict() if line else None,
        "awaiting_confirmation": list(awaiting_confirmation(state)),
        **extra,
    }


def _at(store: SessionStore, session_id: str, supplied: int | None) -> int:
    return store.now_ms(session_id) if supplied is None else supplied


def _register_routes(app: FastAPI) -> FastAPI:  # noqa: C901 - one small handler per route
    @app.get("/health")
    async def health(request: Request, settings: Settings = Depends(_settings)) -> dict[str, Any]:
        return {
            "status": "ok",
            "extractor": request.app.state.extractor.name,
            "livekit_configured": settings.can_mint_tokens,
        }

    @app.post("/session")
    async def create_session(
        req: SessionRequest,
        store: SessionStore = Depends(_store),
        settings: Settings = Depends(_settings),
    ) -> dict[str, Any]:
        session_id = req.session_id or uuid.uuid4().hex[:12]
        if not store.exists(session_id):
            await store.create(session_id, tool_delay_ms=settings.tool_delay_ms)
        room = f"{settings.room_prefix}-{session_id}"
        return _snapshot(
            store,
            session_id,
            store.get(session_id),
            session_id=session_id,
            livekit=livekit_tokens.mint(settings, room=room, identity=req.identity),
        )

    @app.get("/state")
    async def read_state(
        session_id: str = Query(max_length=64), store: SessionStore = Depends(_store)
    ) -> dict[str, Any]:
        return _snapshot(store, session_id, store.get(session_id))

    @app.post("/utterance")
    async def utterance(req: UtteranceRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        at_ms = _at(store, req.session_id, req.at_ms)
        state = await store.apply(
            req.session_id,
            lambda s: verify_unchallenged(next_epoch(s, req.text, at_ms=at_ms, speaker=req.speaker), at_ms),
        )
        return _snapshot(store, req.session_id, state, epoch=state.epoch)

    @app.post("/extract")
    async def extract(
        req: ExtractRequest,
        store: SessionStore = Depends(_store),
        extractor: Extractor = Depends(_extractor),
    ) -> dict[str, Any]:
        delay_ms = store.stress(req.session_id).extract_delay_ms
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        result = await extractor.extract(req.text)
        at_ms = _at(store, req.session_id, req.at_ms)
        seen: dict[str, int] = {}

        def transition(state: TruthState) -> TruthState:
            seen["epoch"] = state.epoch
            return apply_extraction(state, result.candidates, epoch=req.epoch, at_ms=at_ms)

        state = await store.apply(req.session_id, transition)
        return _snapshot(
            store,
            req.session_id,
            state,
            applied=seen["epoch"] == req.epoch,
            requested_epoch=req.epoch,
            source=result.source,
            error=result.error,
            candidates=[
                {"field": c.field, "value": c.value, "inferred": c.inferred, "source_text": c.source_text}
                for c in result.candidates
            ],
        )

    @app.post("/verify")
    async def verify_field(req: VerifyRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        at_ms = _at(store, req.session_id, req.at_ms)
        state = await store.apply(req.session_id, lambda s: verify(s, req.field, at_ms=at_ms, by=req.by))
        return _snapshot(store, req.session_id, state)

    @app.post("/resolve")
    async def resolve(req: ResolveRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        at_ms = _at(store, req.session_id, req.at_ms)
        state = await store.apply(
            req.session_id, lambda s: resolve_conflict(s, req.field, req.value, at_ms=at_ms, by=req.by)
        )
        return _snapshot(store, req.session_id, state)

    @app.post("/delivery")
    async def delivery(req: DeliveryRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        delivered = _delivered(req)
        at_ms = _at(store, req.session_id, req.at_ms)
        state = await store.apply(
            req.session_id,
            lambda s: record_delivery(s, req.field, delivered, at_ms=at_ms, speech_epoch=req.speech_epoch),
        )
        return _snapshot(store, req.session_id, state, delivered=delivered.to_dict())

    @app.post("/provider")
    async def provider(req: ProviderRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        at_ms = _at(store, req.session_id, req.at_ms)
        state = await store.apply(
            req.session_id, lambda s: set_provider(s, req.provider, at_ms=at_ms, reason=req.reason)
        )
        return _snapshot(store, req.session_id, state)

    @app.post("/relay")
    async def relay(req: RelayRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        relay_text = build_relay(store.get(req.session_id), lang=req.lang)
        at_ms = _at(store, req.session_id, req.at_ms)
        fields = [f.field for f in relay_text.facts]
        state = await store.apply(
            req.session_id,
            lambda s: s.with_event(
                "relay_requested",
                at_ms,
                lang=req.lang,
                text=relay_text.text,
                fields=fields,
                withheld=list(relay_text.withheld),
            ),
        )
        return _snapshot(
            store,
            req.session_id,
            state,
            relay={
                "text": relay_text.text,
                "plain": relay_text.plain,
                "lang": req.lang,
                "ready": bool(fields),
                "fields": fields,
                "withheld": list(relay_text.withheld),
                "inline_speed_alpha": relay_text.inline_speed_alpha,
                "completeness": relay_text.completeness,
            },
        )

    @app.post("/stress/tool-delay")
    async def stress(req: ToolDelayRequest, store: SessionStore = Depends(_store)) -> dict[str, Any]:
        key = "tool_delay_ms" if req.target == "tool" else "extract_delay_ms"
        await store.set_stress(req.session_id, **{key: req.delay_ms})
        return _snapshot(store, req.session_id, store.get(req.session_id))

    @app.get("/events")
    async def events(
        session_id: str = Query(max_length=64),
        since: int = Query(default=0, ge=0),
        follow: bool = Query(default=True),
        store: SessionStore = Depends(_store),
    ) -> StreamingResponse:
        store.get(session_id)  # 404 before the stream opens rather than inside it
        return StreamingResponse(
            sse.event_stream(store, session_id, since, follow=follow),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _delivered(req: DeliveryRequest):
    if req.words:
        words = tuple(WordTiming(w.word, w.start_ms, w.end_ms) for w in req.words)
        return cut(words, req.interrupted_at_ms)
    if req.text and req.heard_text is not None:
        return cut_from_text(req.text, req.heard_text)
    return cut(estimate_words(req.text or "", req.duration_ms or 0), req.interrupted_at_ms)


app = create_app()
