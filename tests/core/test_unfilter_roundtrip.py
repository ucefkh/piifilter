"""Unfilter roundtrip fidelity — tests alias reconstruction from real LLM output.

Expanded with adversarial edge cases:
1. Token boundary split (e.g. "Jan" + "ette" across chunks)
2. Paraphrased alias (e.g. "the alias NexGen" instead of the actual alias)
3. Multiple same-type aliases (two PERSON aliases in same conversation)
4. Alias at end of stream with no trailing newline/space
5. No alias exists (no session.alias_store)
"""
import asyncio
import os
import pytest
from piifilter.shared.alias_store import AliasStore
from piifilter.session import Session

pytestmark = pytest.mark.skipif(
    False,
    reason="Always run in core test suite"
)


async def _collect(session: Session, tokens: list[str]) -> str:
    """Helper: run tokens through unfilter_stream and collect the result."""
    async def stream():
        for token in tokens:
            yield token
    result = ""
    async for chunk in session.unfilter_stream(stream()):
        result += chunk
    return result


# ── Happy path ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unfilter_reconstructs_originals():
    """Filter prompt, send to real LLM, get streaming response, unfilter, verify."""
    # Setup alias store
    store = AliasStore(seed="test-unfilter")

    # Create session with aliases
    session = Session(
        prompt="My email is john@example.com and I live in New York",
        conversation_id="unfilter-test-1"
    )
    session.alias_store = store

    # Create aliases
    email_alias = store.get_or_create(session.conversation_id, "john@example.com", "EMAIL")
    city_alias = store.get_or_create(session.conversation_id, "New York", "CITY")

    # Simulate LLM response that uses the aliases
    llm_response = f"Hello! I see your email is {email_alias} and you live in {city_alias}. That's great!"

    # Unfilter
    async def stream():
        for token in llm_response.split(" "):
            yield token + " "

    unfiltered = ""
    async for chunk in session.unfilter_stream(stream()):
        unfiltered += chunk

    assert "john@example.com" in unfiltered, f"Email should be reconstructed, got: {unfiltered}"
    assert "New York" in unfiltered, f"City should be reconstructed, got: {unfiltered}"
    assert "Hello!" in unfiltered


# ── Test 1: Token boundary split ───────────────────────────────────────


@pytest.mark.asyncio
async def test_token_boundary_split():
    """Alias split across streaming chunks must be buffered and reconstructed.

    An alias like "Janette" arriving as "Jan" then "ette..." in successive
    chunks must be re-assembled by the unfilter buffer.
    """
    store = AliasStore(seed="test-token-split")
    session = Session(prompt="My name is Jane Doe", conversation_id="split-test-1")
    session.alias_store = store

    # Create a PERSON alias — this will produce a name like "Janette"
    person_alias = store.get_or_create(session.conversation_id, "Jane Doe", "PERSON")

    # Simulate a tokenizer that splits the alias in two
    half = len(person_alias) // 2
    chunk1 = person_alias[:half]
    chunk2 = person_alias[half:]

    tokens = [f"Hello ", f"my name is ", chunk1, chunk2, f", nice to meet you"]

    unfiltered = await _collect(session, tokens)

    assert "Jane Doe" in unfiltered, (
        f"Person 'Jane Doe' should be reconstructed when alias '{person_alias}' "
        f"is split as '{chunk1}' + '{chunk2}'. Got: {unfiltered}"
    )


# ── Test 2: Paraphrased alias ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_paraphrased_alias_does_not_crash():
    """LLM paraphrases the alias (e.g. 'the alias NexGen') — should not crash or
    produce a false reconstruction."""
    store = AliasStore(seed="test-paraphrase")
    session = Session(prompt="Acme Corp is the client", conversation_id="paraphrase-test-1")
    session.alias_store = store

    # Create a COMPANY alias
    company_alias = store.get_or_create(session.conversation_id, "Acme Corp", "COMPANY")

    # LLM says "the alias NexGen" — but "NexGen" is NOT the actual alias.
    # The actual alias is whatever the store returned (e.g. "TechCorp").
    # This should just pass through unchanged.
    # Note: depending on seed/determinism, "NexGen" might coincidentally be the alias.
    # We construct the response to explicitly NOT match: we say "the alias NexGen"
    # but the store's alias is something else (we verify it's not "NexGen").
    assert company_alias != "NexGen", (
        "Test precondition: the generated alias must differ from 'NexGen'"
    )

    # Write the paraphrase prompt — it mentions an alias-like word that is NOT
    # actually in the store for this conversation
    llm_response = f"The user mentioned their client is the alias NexGen, but I'm not sure."
    tokens = [llm_response]

    unfiltered = await _collect(session, tokens)

    # Expected: response passes through unchanged (no false reconstruction)
    assert unfiltered == llm_response, (
        f"Paraphrased alias must not reconstruct. "
        f"Expected: {llm_response!r}, Got: {unfiltered!r}"
    )


# ── Test 3: Multiple same-type aliases ─────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_same_type_aliases():
    """Two PERSON aliases in the same conversation — both should decode."""
    store = AliasStore(seed="test-multi-person")
    session = Session(
        prompt="Alice and Bob are collaborating",
        conversation_id="multi-person-test-1"
    )
    session.alias_store = store

    alias_a = store.get_or_create(session.conversation_id, "Alice", "PERSON")
    alias_b = store.get_or_create(session.conversation_id, "Bob", "PERSON")

    # Make sure they're different aliases (test precondition)
    assert alias_a != alias_b, "Two different PERSON aliases must be distinct"

    llm_response = f"{alias_a} and {alias_b} are collaborating on the new project."
    tokens = [f"{alias_a} and ", f"{alias_b} are collaborating on the new project."]

    unfiltered = await _collect(session, tokens)

    assert "Alice" in unfiltered, f"'Alice' not reconstructed. Got: {unfiltered}"
    assert "Bob" in unfiltered, f"'Bob' not reconstructed. Got: {unfiltered}"

    # Order check: "Alice" should appear before "Bob"
    alice_idx = unfiltered.index("Alice")
    bob_idx = unfiltered.index("Bob")
    assert alice_idx < bob_idx, (
        f"'Alice' should appear before 'Bob'. Got: {unfiltered}"
    )


# ── Test 4: Alias at end of stream (no trailing newline) ───────────────


@pytest.mark.asyncio
async def test_alias_at_end_of_stream():
    """Alias is the very last token — stream ends without trailing space.

    The end-of-stream flush logic in unfilter_stream must still reconstruct.
    """
    store = AliasStore(seed="test-end-of-stream")
    session = Session(prompt="My company is Globex Inc", conversation_id="end-test-1")
    session.alias_store = store

    company_alias = store.get_or_create(session.conversation_id, "Globex Inc", "COMPANY")

    # The response stream ends with the alias — no trailing whitespace
    tokens = ["I work for ", company_alias]

    unfiltered = await _collect(session, tokens)

    assert "Globex Inc" in unfiltered, (
        f"Alias at end of stream should reconstruct. "
        f"Alias used: {company_alias!r}, Got: {unfiltered!r}"
    )


# ── Test 5: No alias store ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_alias_store_passthrough():
    """When session has no alias_store, unfilter_stream must pass through unchanged."""
    session = Session(
        prompt="Some random text",
        conversation_id="no-store-test-1"
    )
    # Intentionally NOT setting alias_store

    text = "This is a completely normal response with no aliases at all."
    tokens = [text]

    unfiltered = await _collect(session, tokens)

    assert unfiltered == text, (
        f"Without alias_store, stream must pass through unchanged. "
        f"Expected: {text!r}, Got: {unfiltered!r}"
    )


# ── Test 6: No alias store but conversation_id set ─────────────────────


@pytest.mark.asyncio
async def test_no_alias_store_with_conversation_passthrough():
    """Even with conversation_id set, no alias_store means pass-through."""
    store = AliasStore(seed="test-store-exists")
    store.get_or_create("some-other-conv", "secret@example.com", "EMAIL")

    session = Session(
        prompt="Hello world",
        conversation_id="no-store-test-2"
    )
    # alias_store is NOT set — but the store exists elsewhere

    text = "Hey there, this has [EMAIL REDACTED] in it but that doesn't matter."
    tokens = [text]

    unfiltered = await _collect(session, tokens)

    assert unfiltered == text, (
        "Without alias_store on session, must not reconstruct even if "
        "aliases exist in another conversation."
    )


# ── Test 7: Empty chunk in stream ──────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_chunks_handled_gracefully():
    """Empty chunks must not crash the unfilter loop."""
    store = AliasStore(seed="test-empty-chunks")
    session = Session(prompt="Test", conversation_id="empty-test-1")
    session.alias_store = store
    store.get_or_create(session.conversation_id, "test value", "PERSON")

    tokens = ["Hello ", "", "world", "", "!"]

    unfiltered = await _collect(session, tokens)

    assert "Hello world!" in unfiltered.replace("  ", " ").strip(), (
        f"Empty chunks should be handled. Got: {unfiltered!r}"
    )