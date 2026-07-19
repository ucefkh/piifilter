"""Integration tests for streaming pipeline.

Tests the full streaming path:
  - Filter -> stream SSE events
  - Forward -> stream LLM chunks via SSE
  - Unfilter stream with real alias_store

These tests use the real FastAPI test client but mock the provider.
Gated behind PIIFILTER_LIVE_TESTS=1 for the live LLM test.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Skip integration tests unless explicitly requested
pytestmark = pytest.mark.skipif(
    not os.environ.get("PIIFILTER_LIVE_TESTS"),
    reason="Set PIIFILTER_LIVE_TESTS=1 to run streaming integration tests"
)


import pytest
from httpx_sse import aconnect_sse
from piifilter.config import FilterConfig

from piifilter import FilterPipeline, Session
from piifilter.shared.alias_store import AliasStore

# Ensure the REST API module is importable
_api_path = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "rest-api", "src")
if os.path.isdir(_api_path):
    sys.path.insert(0, os.path.abspath(_api_path))

from piifilter_api.server import create_app


# ── Helper: collect all SSE events ──────────────────────────────────────────


async def _collect_sse_events(client: httpx.AsyncClient, url: str, json_body: dict[str, Any]) -> list[dict[str, Any]]:
    """POST to an SSE endpoint and collect all events."""
    events: list[dict[str, Any]] = []
    async with aconnect_sse(client, "POST", url, json=json_body) as sse:
        async for sse_event in sse.aiter_sse():
            try:
                data = json.loads(sse_event.data)
                events.append({"event": sse_event.event, "data": data})
            except (json.JSONDecodeError, TypeError):
                events.append({"event": sse_event.event, "data": sse_event.data})
    return events


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def alias_store() -> AliasStore:
    return AliasStore(seed="test_seed")


@pytest.fixture
def app(alias_store: AliasStore):
    """Create a test FastAPI app."""
    application = create_app()
    # Replace the alias_store with our test one
    application.state.alias_store = alias_store
    application.state.pipeline.alias_store = alias_store
    return application


@pytest.fixture
async def client(app):
    """Async test client."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def pipeline(app):
    return app.state.pipeline


def _setup_alias_conversation(store: AliasStore, conv_id: str) -> None:
    """Register known PII aliases for testing."""
    store.get_or_create(conv_id, "john@example.com", "EMAIL")
    store.get_or_create(conv_id, "555-0100", "PHONE")
    store.get_or_create(conv_id, "NexGen Innovations", "COMPANY")
    store.get_or_create(conv_id, "Sarah Connor", "PERSON")


# ═════════════════════════════════════════════════════════════════════════════
# 1. /v1/filter/stream endpoint
# ═════════════════════════════════════════════════════════════════════════════


class TestFilterStreamEndpoint:
    """POST /v1/filter/stream — returns SSE events."""

    async def test_filter_stream_basic(self, client):
        """Basic filter stream with no PII."""
        events = await _collect_sse_events(client, "/v1/filter/stream", {
            "prompt": "Hello, how are you?",
        })
        assert len(events) >= 2
        # First event should be "filtered"
        first_event = events[0]
        assert first_event["event"] == "message"
        assert first_event["data"]["type"] == "filtered"
        assert "filtered_prompt" in first_event["data"]["data"]
        # Last event should be "done"
        last_event = events[-1]
        assert last_event["data"]["type"] == "done"

    async def test_filter_stream_with_entity_found(self, client, alias_store):
        """Filter stream detects PII and returns filtered prompt."""
        # First create a conversation with aliases
        _setup_alias_conversation(alias_store, "conv-stream-1")

        events = await _collect_sse_events(client, "/v1/filter/stream", {
            "prompt": "My email is john@example.com",
            "conversation_id": "conv-stream-1",
        })
        assert len(events) >= 2
        first = events[0]
        assert first["data"]["type"] == "filtered"
        assert first["data"]["data"]["entity_count"] >= 1

    async def test_filter_stream_blocked(self, client):
        """Filter stream emits blocked event when blocked."""
        events = await _collect_sse_events(client, "/v1/filter/stream", {
            "prompt": "My API key is sk-abc123def456",
        })
        # Should have filtered and blocked events
        blocked_events = [e for e in events if e["data"]["type"] == "blocked"]
        assert len(blocked_events) >= 1

    async def test_filter_stream_empty_prompt(self, client):
        """Empty prompt is handled gracefully."""
        events = await _collect_sse_events(client, "/v1/filter/stream", {
            "prompt": "",
        })
        assert len(events) >= 2
        assert events[-1]["data"]["type"] == "done"


# ═════════════════════════════════════════════════════════════════════════════
# 2. /v1/forward/stream endpoint
# ═════════════════════════════════════════════════════════════════════════════


class TestForwardStreamEndpoint:
    """POST /v1/forward/stream — filters and forwards to LLM in streaming mode."""

    async def test_forward_stream_no_provider(self, client):
        """Without a registered provider, gets a block/error."""
        events = await _collect_sse_events(client, "/v1/forward/stream", {
            "prompt": "Hello world",
        })
        # Should fail with no provider
        has_error = any(e["data"]["type"] == "error" for e in events)
        has_blocked = any(e["data"]["type"] == "blocked" for e in events)
        assert has_error or has_blocked


# ═════════════════════════════════════════════════════════════════════════════
# 3. /v1/unfilter/stream endpoint
# ═════════════════════════════════════════════════════════════════════════════


class TestUnfilterStreamEndpoint:
    """POST /v1/unfilter/stream — streaming unfilter via SSE."""

    async def test_unfilter_stream_basic(self, client, alias_store):
        """Basic unfilter stream restores aliases."""
        _setup_alias_conversation(alias_store, "conv-unfilter-1")

        # Get the actual alias values
        aliases = alias_store.get_all("conv-unfilter-1")
        email_alias = aliases["john@example.com"]

        events = await _collect_sse_events(client, "/v1/unfilter/stream", {
            "conversation_id": "conv-unfilter-1",
            "stream": ["Contact: ", email_alias, " for details."],
        })
        assert len(events) >= 2
        # Should have restored the original
        chunk_events = [e for e in events if e["data"]["type"] == "chunk"]
        assert len(chunk_events) > 0
        done_event = [e for e in events if e["data"]["type"] == "done"]
        assert len(done_event) == 1
        assert done_event[0]["data"]["data"]["chunks"] > 0

    async def test_unfilter_stream_multiple_aliases(self, client, alias_store):
        """Multiple aliases in stream get restored."""
        _setup_alias_conversation(alias_store, "conv-unfilter-2")
        aliases = alias_store.get_all("conv-unfilter-2")
        company_alias = aliases["NexGen Innovations"]
        person_alias = aliases["Sarah Connor"]

        events = await _collect_sse_events(client, "/v1/unfilter/stream", {
            "conversation_id": "conv-unfilter-2",
            "stream": [
                "The company ",
                company_alias[:5],
                company_alias[5:],
                " was founded by ",
                person_alias[:7],
                person_alias[7:],
                ".",
            ],
        })
        # Collect the unfiltered text
        text_parts: list[str] = []
        for e in events:
            if e["data"]["type"] == "chunk":
                text_parts.append(e["data"]["data"]["text"])
        result = "".join(text_parts)
        assert "NexGen Innovations" in result
        assert "Sarah Connor" in result

    async def test_unfilter_stream_no_aliases(self, client, alias_store):
        """Conversation with no aliases passes through."""
        conv_id = "conv-unfilter-empty"
        events = await _collect_sse_events(client, "/v1/unfilter/stream", {
            "conversation_id": conv_id,
            "stream": ["Just ", "some ", "text."],
        })
        text_parts: list[str] = []
        for e in events:
            if e["data"]["type"] == "chunk":
                text_parts.append(e["data"]["data"]["text"])
        result = "".join(text_parts)
        assert result == "Just some text."

    async def test_unfilter_stream_empty(self, client, alias_store):
        """Empty stream yields only a done event."""
        _setup_alias_conversation(alias_store, "conv-unfilter-empty2")
        events = await _collect_sse_events(client, "/v1/unfilter/stream", {
            "conversation_id": "conv-unfilter-empty2",
            "stream": [],
        })
        assert len(events) == 1
        assert events[0]["data"]["type"] == "done"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Live LLM integration test (gated)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not os.environ.get("PIIFILTER_LIVE_TESTS"),
    reason="Set PIIFILTER_LIVE_TESTS=1 to run live LLM tests",
)
class TestLiveStreaming:
    """Integration test with a real LLM provider.

    Requires PIIFILTER_LIVE_TESTS=1 and a working provider config.
    """

    async def test_live_forward_stream(self, app):
        """Forward stream with a real provider yields chunks."""
        pipeline = app.state.pipeline
        config = app.state.config

        # Get the configured provider
        provider_name = config.provider.name
        provider = pipeline.registry.get_provider_or_none(provider_name)

        if provider is None:
            pytest.skip(f"Provider '{provider_name}' not registered")

        # Create a session
        s = Session(
            prompt="Hello, tell me a one-sentence fact about the moon.",
            provider_config=config.provider,
        )

        # Run pipeline first (no LLM call yet, just filtering)
        s = await pipeline.run(s)

        if s.is_blocked:
            pytest.skip("Pipeline blocked the request")

        # Now stream from the provider
        chunks: list[str] = []
        async for chunk in provider.forward_stream(s):
            chunks.append(chunk)

        assert len(chunks) >= 1
        full_text = "".join(chunks)
        assert len(full_text) > 0

    async def test_live_unfilter_stream(self, app, alias_store):
        """Full pipe: filter -> forward -> unfilter stream."""
        pipeline = app.state.pipeline
        config = app.state.config

        provider_name = config.provider.name
        provider = pipeline.registry.get_provider_or_none(provider_name)

        if provider is None:
            pytest.skip(f"Provider '{provider_name}' not registered")

        conv_id = "live-unfilter-test"

        # Create a session with PII that gets aliased
        s = Session(
            prompt="My email is john@example.com and I work at NexGen Innovations.",
            conversation_id=conv_id,
            provider_config=config.provider,
        )
        s.alias_store = alias_store

        # Run pipeline
        s = await pipeline.run(s)

        if s.is_blocked:
            pytest.skip("Pipeline blocked the request — no PII to test unfilter")

        # Build a prompt that uses the aliases
        aliases = alias_store.get_all(conv_id)
        if not aliases:
            pytest.skip("No aliases were created — all PII was blocked?")

        # Create a new session to ask about the aliased entities
        s2 = Session(
            prompt=f"Who works at {list(aliases.values())[0]}?",
            conversation_id=conv_id,
            provider_config=config.provider,
        )
        s2.alias_store = alias_store

        # Run pipeline (filter + forward)
        s2 = await pipeline.run(s2)

        if s2.is_blocked or not s2.llm_response:
            pytest.skip("Pipeline blocked or no response")

        # Now test unfilter on the response
        s3 = Session(
            prompt="",
            conversation_id=conv_id,
        )
        s3.alias_store = alias_store

        # Create a stream from the LLM response (split into words as simulated tokens)
        response_tokens = s2.llm_response.split(" ")
        async def response_stream():
            for token in response_tokens:
                yield token + " "

        unfiltered = ""
        async for chunk in s3.unfilter_stream(response_stream()):
            unfiltered += chunk

        assert len(unfiltered) > 0