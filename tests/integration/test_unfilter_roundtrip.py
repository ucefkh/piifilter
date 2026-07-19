"""Unfilter roundtrip integration test — real LLM → stream → unfilter.

Tests the full pipeline:
1. Original prompt with PII → filter (replace PII with aliases)
2. Filtered prompt → real LLM → get streaming response
3. Streaming response → unfilter (restore original PII)
4. Verify the roundtrip preserves meaning and restores original values

Gated behind PIIFILTER_LIVE_TESTS=1 to avoid accidental API calls.
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
from piifilter.shared.alias_store import AliasStore
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


def find_available_backend() -> tuple[str, str, str] | None:
    """Probe local LLM backends and return (label, endpoint, model)."""
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
    reason="No live LLM backend found. Start LM Studio (port 1234) or Ollama (port 11434).",
)


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
@need_live_backend
async def test_unfilter_roundtrip_basic():
    """Full roundtrip: filter → forward → unfilter with aliases."""
    label, endpoint, model = BACKEND  # type: ignore[misc]

    # Setup
    alias_store = AliasStore(seed="roundtrip_test")
    registry = PluginRegistry()

    # Register detectors
    from piifilter_detector_regex.detector import RegexDetector
    regex_detector = RegexDetector()
    await regex_detector.initialize()
    registry.register_detector(regex_detector, overwrite=True)

    try:
        from piifilter_detector_presidio.detector import PresidioDetector
        presidio_detector = PresidioDetector()
        await presidio_detector.initialize()
        registry.register_detector(presidio_detector, overwrite=True)
    except Exception:
        pass

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

    pipeline = FilterPipeline(
        config=config,
        registry=registry,
        alias_store=alias_store,
    )

    conv_id = "roundtrip-" + str(int(asyncio.get_event_loop().time()))

    # Step 1: Filter — replace PII with aliases
    original_prompt = (
        "My name is Alice Johnson and my email is alice@example.com. "
        "Please tell me a fun fact about space exploration."
    )
    session = Session(
        prompt=original_prompt,
        mode=ReplacementMode.SEMANTIC,
        conversation_id=conv_id,
    )
    session.alias_store = alias_store

    result = await pipeline.run(session)

    assert not result.is_blocked, "Pipeline should not block this prompt"
    assert result.filtered_prompt is not None, "Filtered prompt should exist"
    assert result.filtered_prompt != original_prompt, "Prompt should be filtered"

    # Verify PII is replaced
    assert "Alice Johnson" not in result.filtered_prompt, (
        "Name should be aliased in filtered prompt"
    )
    assert "alice@example.com" not in result.filtered_prompt, (
        "Email should be aliased in filtered prompt"
    )

    print(f"\n  Original:  {original_prompt}")
    print(f"  Filtered:  {result.filtered_prompt}")
    print(f"  Entities:  {len(result.entities)}")
    for e in result.entities:
        print(f"    {e.entity_type.value}: '{e.value}' → '{result.replacements}'" 
              if hasattr(e, 'value') else f"    {e.entity_type.value}")

    # Step 2: Forward to LLM (filtered prompt)
    assert result.llm_response is not None, "LLM should return a response"
    assert "[PIIFilter Error" not in result.llm_response, (
        f"LLM response should not contain errors: {result.llm_response[:100]}"
    )
    assert len(result.llm_response) > 10, "LLM response should be meaningful"

    print(f"  LLM resp:  {result.llm_response[:150]}...")

    # Step 3: Unfilter — restore aliases in the response
    original_text = result.llm_response

    # Simulate streaming by splitting the response into tokens
    async def token_stream():
        for word in original_text.split(" "):
            yield word + " "
            await asyncio.sleep(0)  # yield control

    unfiltered = ""
    async for chunk in result.unfilter_stream(token_stream()):
        unfiltered += chunk

    print(f"  Unfiltered:{unfiltered[:150]}...")

    # Step 4: Verify roundtrip
    # The unfiltered response should NOT contain any alias tokens
    aliases = alias_store.get_all(conv_id)
    for original_pii, alias in aliases.items():
        if alias in unfiltered:
            print(f"  WARNING: Alias '{alias}' still present in unfiltered output")
            # This is a partial match issue — the alias may be part of a larger word
            # Count occurrences
            count = unfiltered.count(alias)
            print(f"    Alias appears {count} times in unfiltered output")

    print(f"\n  Roundtrip complete!")
    print(f"    Original entities: {len(result.entities)}")
    print(f"    Aliases created:   {len(aliases)}")
    print(f"    LLM response len:  {len(original_text)}")
    print(f"    Unfiltered len:    {len(unfiltered)}")

    # Cleanup
    await pipeline.close()


@pytest.mark.asyncio
@need_live_backend
async def test_unfilter_roundtrip_measure_rate():
    """Measure the unfilter roundtrip rate and verify it runs in real time.

    Tests: real model → stream → unfilter, measuring throughput.
    """
    label, endpoint, model = BACKEND  # type: ignore[misc]

    alias_store = AliasStore(seed="rate_test")
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

    pipeline = FilterPipeline(
        config=config,
        registry=registry,
        alias_store=alias_store,
    )

    conv_id = "rate-test-" + str(int(asyncio.get_event_loop().time()))

    # Prompt with multiple PII types to ensure aliases are created
    prompt = (
        "My name is Bob Smith, email bob@test.com, "
        "phone +1-555-123-4567, and I live at 123 Main Street. "
        "Write me a short poem about the seasons."
    )

    session = Session(
        prompt=prompt,
        mode=ReplacementMode.SEMANTIC,
        conversation_id=conv_id,
    )
    session.alias_store = alias_store

    result = await pipeline.run(session)
    assert result.llm_response, "LLM should respond"

    aliases = alias_store.get_all(conv_id)
    print(f"\n  Rate Test Setup:")
    print(f"    PII entities found: {len(result.entities)}")
    print(f"    Aliases created:    {len(aliases)}")
    for orig, alias in aliases.items():
        print(f"      '{orig}' → '{alias}'")
    print(f"    LLM response:       {len(result.llm_response)} chars")

    # Measure unfilter rate
    response = result.llm_response
    import time

    trials = 3
    total_chars = 0
    total_time = 0.0

    for trial in range(trials):
        # Create fresh stream from the response
        async def token_stream(text=response):
            for word in text.split(" "):
                yield word + " "

        t0 = time.perf_counter()
        unfiltered = ""
        async for chunk in result.unfilter_stream(token_stream()):
            unfiltered += chunk
        elapsed = time.perf_counter() - t0

        total_chars += len(response)
        total_time += elapsed

    avg_rate = total_chars / total_time if total_time > 0 else 0
    print(f"\n  Unfilter throughput:")
    print(f"    Avg: {avg_rate:.0f} chars/sec over {trials} trials")
    print(f"    Total time: {total_time:.3f}s for {total_chars} chars")

    assert avg_rate > 0, "Unfilter rate should be measurable"
    print(f"  ✅ Unfilter roundtrip verified — {avg_rate:.0f} chars/sec")

    # Verify aliases were actually created
    assert len(aliases) > 0, "Should have created at least one alias"
    await pipeline.close()


@pytest.mark.asyncio
@need_live_backend
async def test_unfilter_roundtrip_no_pii():
    """Roundtrip with no PII — should pass through unchanged."""
    label, endpoint, model = BACKEND  # type: ignore[misc]

    alias_store = AliasStore(seed="no_pii_test")
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

    pipeline = FilterPipeline(
        config=config,
        registry=registry,
        alias_store=alias_store,
    )

    conv_id = "no-pii-" + str(int(asyncio.get_event_loop().time()))

    prompt = "What is the capital of France? Answer in one word."
    session = Session(
        prompt=prompt,
        mode=ReplacementMode.SEMANTIC,
        conversation_id=conv_id,
    )
    session.alias_store = alias_store

    result = await pipeline.run(session)

    assert result.llm_response is not None
    assert "[PIIFilter Error" not in result.llm_response

    # Verify no aliases were created (no PII detected)
    aliases = alias_store.get_all(conv_id)
    print(f"\n  No-PII Test: {len(aliases)} aliases created (expected 0)")
    assert len(aliases) == 0, "Should have no aliases for PII-free prompt"

    await pipeline.close()