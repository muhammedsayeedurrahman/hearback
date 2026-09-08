import httpx
import pytest

from agent.client import HearbackClient
from api.extraction import RuleExtractor
from api.main import create_app
from api.settings import Settings


def offline_settings() -> Settings:
    return Settings(
        anthropic_api_key=None,
        extraction_model="none",
        extractor="rules",
        livekit_url=None,
        livekit_api_key=None,
        livekit_api_secret=None,
        tool_delay_ms=0,
        room_prefix="test",
        cors_origins=(),
    )


@pytest.fixture
async def hearback():
    """A real sidecar, in-process: the agent's HTTP contract is exercised, not mocked."""
    app = create_app(extractor=RuleExtractor(), settings=offline_settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://hearback") as http:
        client = HearbackClient(client=http)
        await client.create_session("s_agent")
        yield client
