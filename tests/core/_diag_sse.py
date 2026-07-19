"""Quick diagnostic for SSE — placed inside the project test dir."""
import sys, os
# Add API path
_api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "apps", "rest-api", "src"))
sys.path.insert(0, _api_path)

import json
import httpx
import pytest
from httpx_sse import aconnect_sse
from piifilter.shared.alias_store import AliasStore
from piifilter_api.server import create_app


@pytest.fixture
def alias_store():
    return AliasStore(seed="test_seed")


@pytest.fixture
def app(alias_store):
    application = create_app()
    application.state.alias_store = alias_store
    application.state.pipeline.alias_store = alias_store
    return application


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


async def test_sse_raw(client):
    """Check what the endpoint actually returns."""
    async with client.stream("POST", "/v1/filter/stream", json={"prompt": "Hello"}) as resp:
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        body = await resp.aread()
        print(f"Body: {body}")
        assert resp.status_code == 200