"""Integration test — runs against a REAL LLM if available.

Auto-detects local backends (LM Studio → Ollama) and runs the full
pipeline: detect PII → filter → forward to LLM → unfilter response.

Gated behind ``PIIFILTER_LIVE_TESTS=1`` to avoid accidental API calls.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import pytest

from piifilter.config import FilterConfig, ProviderConfig
from piifilter.pipeline import FilterPipeline
from piifilter.registry.registry import PluginRegistry
from piifilter.session import Session
from piifilter.shared.models import ReplacementMode

# ── Skip guard ─────────────────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    not os.environ.get("PIIFILTER_LIVE_TESTS"),
    reason="Set PIIFILTER_LIVE_TESTS=1 to run live LLM tests",
)

# ── Backend detection ──────────────────────────────────────────────

ENDPOINTS = {
    "LM Studio": "http://localhost:1234/v1",
    "Ollama": "http://localhost:11434/v1",
}

TIMEOUT_S = float(os.environ.get("PIIFILTER_LIVE_TIMEOUT", "120"))


def find_available_backend() -> tuple[str, str, str] | None:
    """Probe local LLM backends and return ``(label, endpoint, model)``.

    Tries LM Studio first, then Ollama. Returns ``None`` if no backend
    is reachable.
    """
    for label, endpoint in ENDPOINTS.items():
        try:
            resp = httpx.get(f"{endpoint}/models", timeout=3.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue

        models_raw = data.get("data") or data.get("models") or []

        first_model: str | None = None
        for item in models_raw:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name") or item.get("model")
                if mid:
                    first_model = str(mid)
                    break

        if first_model:
            return (label, endpoint, first_model)

    return None


BACKEND = find_available_backend()

need_live_backend = pytest.mark.skipif(
    BACKEND is None,
    reason=(
        "No live LLM backend found. Start LM Studio (port 1234) "
        "or Ollama (port 11434) and try again."
    ),
)


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
@need_live_backend
async def test_provider_auto_detect():
    """Provider should auto-detect the running backend and list models."""
    from piifilter_provider_lmstudio.provider import LMStudioProvider

    p = LMStudioProvider()
    await p.initialize()
    try:
        assert p._detected_endpoint is not None, "Should detect a backend"
        assert p._detected_model is not None, "Should detect at least one model"
        assert await p.check_health(), "Health check should pass"
    finally:
        await p.shutdown()


@pytest.mark.asyncio
@need_live_backend
async def test_provider_forward_real():
    """Send a real prompt to the LLM and verify it gets a meaningful response."""
    from piifilter_provider_lmstudio.provider import LMStudioProvider

    label, endpoint, model = BACKEND  # type: ignore[misc]

    p = LMStudioProvider()
    await p.initialize()
    try:
        session = Session(
            prompt="Say 'Hello from PIIFilter!' and nothing else.",
            filtered_prompt="Say 'Hello from PIIFilter!' and nothing else.",
            provider_config=ProviderConfig(
                name="lmstudio",
                endpoint=endpoint,
                default_model=model,
            ),
        )

        response = await p.forward(session)
        assert response, "LLM should return a non-empty response"
        assert "[PIIFilter Error" not in response, (
            f"Response should not contain an error message: {response}"
        )
        assert len(response) > 5, "Response should be meaningful"
    finally:
        await p.shutdown()


@pytest.mark.asyncio
@need_live_backend
async def test_provider_forward_end_to_end():
    """Full pipeline: detect → filter → forward → unfilter.

    Tests a non-trivial chain: the provider must run through the pipeline
    with the PIIFilter core, register the plugin, and produce a filtered
    response from the LLM.
    """
    label, endpoint, model = BACKEND  # type: ignore[misc]

    config = FilterConfig()
    config.provider = ProviderConfig(
        name="lmstudio",
        endpoint=endpoint,
        default_model=model,
    )

    registry = PluginRegistry()
    # Register the LM Studio provider so the pipeline can find it
    from piifilter_provider_lmstudio.provider import LMStudioProvider

    provider = LMStudioProvider()
    await provider.initialize()
    registry.register_provider(provider, overwrite=True)

    pipeline = FilterPipeline(config=config, registry=registry)

    prompt = (
        "Hi! My name is Sarah Connor and my email is sarah@resistance.org. "
        "What's your name?"
    )
    session = Session(
        prompt=prompt,
        mode=ReplacementMode.SEMANTIC,
        provider_config=ProviderConfig(
            name="lmstudio",
            endpoint=endpoint,
            default_model=model,
        ),
        conversation_id="test-e2e-" + str(int(asyncio.get_event_loop().time())),
    )

    result = await pipeline.run(session)

    # 1. Verify detection/filtering
    assert result.filtered_prompt is not None, "Filtered prompt should not be None"
    assert result.filtered_prompt != prompt, "Prompt should have been filtered"

    # The original PII should NOT appear in the filtered prompt
    assert "Sarah Connor" not in result.filtered_prompt, (
        "Name should have been filtered out"
    )
    assert "sarah@resistance.org" not in result.filtered_prompt, (
        "Email should have been filtered out"
    )

    print(f"\n  Original:       {prompt}")
    print(f"  Filtered:       {result.filtered_prompt}")
    print(f"  Entities found: {len(result.entities)}")
    for e in result.entities:
        print(f"    {e.entity_type.value}: '{e.value}'")

    # 2. Verify forward (LLM response)
    assert result.llm_response is not None, "LLM should have returned a response"
    assert "[PIIFilter Error" not in result.llm_response, (
        f"LLM response should not contain an error: {result.llm_response}"
    )
    assert len(result.llm_response) > 5, "LLM response should be meaningful"
    print(f"  LLM response:   {result.llm_response[:200]}...")

    # 3. Verify unfilter (alias restoration)
    unfiltered = result.replace_in_response(result.llm_response)
    if unfiltered != result.llm_response:
        print(f"  Unfiltered:     {unfiltered[:200]}...")
    else:
        print("  (No aliases to restore in response)")


@pytest.mark.asyncio
@need_live_backend
async def test_provider_health_check():
    """Health check should reflect the real backend."""
    from piifilter_provider_lmstudio.provider import LMStudioProvider

    p = LMStudioProvider()
    await p.initialize()
    try:
        healthy = await p.check_health()
        assert healthy is True, "Health check should pass against live backend"
    finally:
        await p.shutdown()


@pytest.mark.asyncio
async def test_provider_forward_empty_prompt():
    """Empty filtered prompt should return empty string."""
    from piifilter_provider_lmstudio.provider import LMStudioProvider

    p = LMStudioProvider()
    await p.initialize()
    try:
        session = Session(
            prompt="",
            filtered_prompt="",
        )
        response = await p.forward(session)
        assert response == "", "Empty prompt should return empty response"
    finally:
        await p.shutdown()


@pytest.mark.asyncio
async def test_provider_forward_bad_endpoint():
    """Invalid endpoint should return a PIIFilter error message."""
    from piifilter_provider_lmstudio.provider import LMStudioProvider

    p = LMStudioProvider()
    await p.initialize()
    try:
        session = Session(
            prompt="Hello",
            filtered_prompt="Hello",
            provider_config=ProviderConfig(
                name="lmstudio",
                endpoint="http://localhost:19999/v1",
                default_model="test-model",
            ),
        )
        response = await p.forward(session)
        assert "[PIIFilter Error" in response, (
            "Bad endpoint should produce error message"
        )
    finally:
        await p.shutdown()


if __name__ == "__main__":
    """Manual runner — used for quick smoke tests."""
    async def main():
        import sys

        # Set the env var so the skip guards don't fire
        os.environ["PIIFILTER_LIVE_TESTS"] = "1"

        label, endpoint, model = BACKEND  # type: ignore[misc]
        registry = PluginRegistry()

        from piifilter_provider_lmstudio.provider import LMStudioProvider
        provider = LMStudioProvider()
        await provider.initialize()
        registry.register_provider(provider, overwrite=True)

        config = FilterConfig()
        config.provider = ProviderConfig(
            name="lmstudio",
            endpoint=endpoint,
            default_model=model,
        )

        pipeline = FilterPipeline(config=config, registry=registry)

        session = Session(
            prompt="My phone is +1-555-123-4567 and I live at 742 Elm Street.",
            mode=ReplacementMode.SEMANTIC,
            provider_config=ProviderConfig(
                name="lmstudio",
                endpoint=endpoint,
                default_model=model,
            ),
            conversation_id="test-manual-runner",
        )

        result = await pipeline.run(session)

        print(f"\n=== RESULTS ===")
        print(f"Original:     {session.prompt}")
        print(f"Filtered:     {result.filtered_prompt}")
        print(f"LLM Response: {result.llm_response[:300] if result.llm_response else 'N/A'}...")
        print(f"Entities:     {len(result.entities)}")
        for e in result.entities:
            print(f"  {e.entity_type.value}: '{e.value}'")

        await pipeline.close()

    asyncio.run(main())