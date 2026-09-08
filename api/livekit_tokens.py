"""LiveKit access tokens. The API key and secret never leave the server."""

from __future__ import annotations

import logging
from typing import Any

from api.settings import Settings

logger = logging.getLogger(__name__)


def mint(settings: Settings, room: str, identity: str, ttl_minutes: int = 60) -> dict[str, Any]:
    """Return a join token, or a reason the client can display instead of failing silently."""
    if not settings.can_mint_tokens:
        return {"url": settings.livekit_url, "room": room, "token": None, "reason": "LiveKit credentials not configured"}
    try:
        from datetime import timedelta

        from livekit import api

        token = (
            api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(identity)
            .with_name(identity)
            .with_ttl(timedelta(minutes=ttl_minutes))
            .with_grants(api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
            .to_jwt()
        )
    except Exception as exc:
        logger.warning("could not mint a LiveKit token: %s", exc)
        return {"url": settings.livekit_url, "room": room, "token": None, "reason": str(exc)}
    return {"url": settings.livekit_url, "room": room, "token": token, "identity": identity, "reason": None}
