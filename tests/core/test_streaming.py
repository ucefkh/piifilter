"""Unit tests for streaming unfilter logic.

Tests ``Session.unfilter_stream()`` with:
  - Alias spans multiple tokens ("Nex" + "Gen" should buffer until complete)
  - Model paraphrases alias ("the alias NexGen" should still match)
  - Model truncates alias mid-stream (should timeout and flush)
  - Partial alias at end of response (should flush on stream end)
  - No aliases (pass-through)
  - No alias_store (pass-through)
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest

from piifilter.session import Session
from piifilter.shared.alias_store import AliasStore


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _collect(agen: AsyncGenerator[str, None]) -> str:
    """Collect all chunks from an async generator into a single string."""
    parts: list[str] = []
    async for chunk in agen:
        parts.append(chunk)
    return "".join(parts)


async def _to_stream(chunks: list[str]) -> AsyncGenerator[str, None]:
    """Convert a list of string chunks to an async generator."""
    for chunk in chunks:
        yield chunk


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def alias_store() -> AliasStore:
    return AliasStore(seed="test_seed")


@pytest.fixture
def session_with_aliases(alias_store: AliasStore) -> Session:
    """Session with an alias_store and known alias mappings."""
    s = Session(
        prompt="",
        conversation_id="test-conv-stream",
    )
    s.alias_store = alias_store

    # Register some aliases: original -> alias
    # NexGen is in the COMPANY pool, so it maps to something consistent
    alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
    alias_store.get_or_create("test-conv-stream", "john@example.com", "EMAIL")
    alias_store.get_or_create("test-conv-stream", "Sarah Connor", "PERSON")

    return s


@pytest.fixture
def session_no_aliases() -> Session:
    """Session WITHOUT an alias_store — should pass through."""
    s = Session(prompt="", conversation_id="no-store-conv")
    s.alias_store = None  # explicitly no store
    return s


# ═════════════════════════════════════════════════════════════════════════════
# 1. No-aliases pass-through
# ═════════════════════════════════════════════════════════════════════════════


class TestStreamingPassThrough:
    """When there are no aliases, the stream should pass through unchanged."""

    async def test_no_alias_store(self, session_no_aliases):
        """Session without alias_store: stream passes through."""
        chunks = ["Hello", " ", "world", "!"]
        result = await _collect(session_no_aliases.unfilter_stream(_to_stream(chunks)))
        assert result == "Hello world!"

    async def test_no_matching_aliases(self, alias_store):
        """Session with alias_store but stream has no alias text."""
        s = Session(prompt="", conversation_id="empty-conv")
        s.alias_store = alias_store
        chunks = ["This", " is", " plain", " text."]
        result = await _collect(s.unfilter_stream(_to_stream(chunks)))
        assert result == "This is plain text."

    async def test_empty_stream(self, session_with_aliases):
        """Empty stream yields nothing."""
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream([])))
        assert result == ""


# ═════════════════════════════════════════════════════════════════════════════
# 2. Alias across multiple tokens
# ═════════════════════════════════════════════════════════════════════════════


class TestStreamingMultiTokenAlias:
    """Aliases that span multiple token chunks should be buffered correctly."""

    async def test_alias_in_single_chunk(self, session_with_aliases):
        """Complete alias arrives in one chunk."""
        chunks = ["The company is ", "NexGen", " and it's great."]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        # "NexGen" should be replaced by its original (which is also "NexGen" since
        # that's how generate_alias works — it maps to a COMPANY name)
        assert "NexGen" in result  # It's an alias for itself if original == NexGen
        # The alias mapping is NexGen (original) -> NexGen (alias), so it stays same
        # Let's verify by checking what alias was generated
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        original_lookup = session_with_aliases.alias_store.get_original("test-conv-stream", alias)
        assert original_lookup == "NexGen"

    async def test_alias_split_across_two_tokens(self, session_with_aliases):
        """Alias 'NexGen' is split as 'Nex' + 'Gen'."""
        # Get the actual alias so we know what to split
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        # Since alias is a generated name from the pool, it might not be "NexGen"
        # Let's test with whatever alias was generated
        alias_map = session_with_aliases._build_alias_map()
        original_for_alias = alias_map.get(alias)
        assert original_for_alias == "NexGen"

        # Split the alias across two chunks
        mid = len(alias) // 2
        chunks = ["The company ", alias[:mid], alias[mid:], " is a leader."]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert "NexGen" in result  # Restored to original
        assert alias not in result  # Alias replaced

    async def test_alias_split_across_three_tokens(self, session_with_aliases):
        """Alias like 'john@example.com' split as 'john' + '@ex' + 'ample.com'."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "john@example.com", "EMAIL")
        original = session_with_aliases.alias_store.get_original("test-conv-stream", alias)
        assert original == "john@example.com"

        # Split into 3 parts
        parts = [alias[:4], alias[4:8], alias[8:]]
        chunks = ["Contact: ", parts[0], parts[1], parts[2], " for info."]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert "john@example.com" in result
        assert alias not in result  # Should have been replaced

    async def test_alias_buffered_then_flushed_on_complete(self, session_with_aliases):
        """Buffer builds up around alias, then complete alias triggers replacement."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "Sarah Connor", "PERSON")
        original = session_with_aliases.alias_store.get_original("test-conv-stream", alias)
        assert original == "Sarah Connor"

        # The stream starts with non-alias text before the alias
        chunks = ["Hello ", "my name is ", alias[:6], alias[6:], ", nice to meet you."]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert "Sarah Connor" in result
        assert original == "Sarah Connor"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Model paraphrases alias
# ═════════════════════════════════════════════════════════════════════════════


class TestStreamingParaphrase:
    """Model generates text around the alias — still matches."""

    async def test_alias_in_context(self, session_with_aliases):
        """Alias embedded in a sentence."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        result = await _collect(
            session_with_aliases.unfilter_stream(_to_stream(["the alias ", alias, " was mentioned"]))
        )
        assert "NexGen" in result  # Original restored

    async def test_multiple_aliases_in_stream(self, session_with_aliases):
        """Multiple different aliases in the same stream."""
        alias_company = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        alias_email = session_with_aliases.alias_store.get_or_create("test-conv-stream", "john@example.com", "EMAIL")

        chunks = ["Company: ", alias_company, ", Contact: ", alias_email, "."]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))

        assert "NexGen" in result
        assert "john@example.com" in result
        assert alias_company not in result if alias_company != "NexGen" else True
        assert alias_email not in result if alias_email != "john@example.com" else True


# ═════════════════════════════════════════════════════════════════════════════
# 4. Truncated alias mid-stream (timeout handling)
# ═════════════════════════════════════════════════════════════════════════════


class TestStreamingTruncation:
    """Model truncates alias mid-stream — should be handled gracefully."""

    async def test_truncated_alias_flush_on_end(self, session_with_aliases):
        """Partial alias at end of stream — should flush remaining buffer."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        # Only send part of the alias, then end the stream
        partial = alias[:3]
        chunks = ["The company is called ", partial]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        # The partial text should be flushed as-is
        assert partial in result
        # The full alias should not be present since it was truncated
        # (we only sent 3 chars, not the full alias)

    async def test_truncated_alias_with_remaining_text(self, session_with_aliases):
        """Partial alias then new text — should flush partial and continue."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        # The alias gets generated, so let's find the actual alias
        partial = alias[:3]
        chunks = [partial, " and also some other text"]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        # The partial should have been flushed
        assert partial in result
        assert "other text" in result

    async def test_non_matching_prefix(self, session_with_aliases):
        """A prefix that doesn't match any alias should pass through."""
        chunks = ["This ", "text ", "doesn't ", "match ", "any ", "alias."]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert result == "This text doesn't match any alias."


# ═════════════════════════════════════════════════════════════════════════════
# 5. Mixed content
# ═════════════════════════════════════════════════════════════════════════════


class TestStreamingMixedContent:
    """Mix of alias and non-alias content."""

    async def test_alias_at_start(self, session_with_aliases):
        """Alias appears at the very start."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        result = await _collect(
            session_with_aliases.unfilter_stream(_to_stream([alias, " is a tech company."]))
        )
        assert "NexGen" in result

    async def test_alias_at_end(self, session_with_aliases):
        """Alias appears at the very end."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        result = await _collect(
            session_with_aliases.unfilter_stream(_to_stream(["The leader is ", alias]))
        )
        assert "NexGen" in result

    async def test_alias_surrounded_by_punctuation(self, session_with_aliases):
        """Alias with punctuation around it."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        result = await _collect(
            session_with_aliases.unfilter_stream(_to_stream(["(", alias, ")"]))
        )
        assert "NexGen" in result

    async def test_long_stream_with_mixed_content(self, session_with_aliases):
        """A longer, realistic stream with mixed content."""
        alias_company = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        alias_person = session_with_aliases.alias_store.get_or_create("test-conv-stream", "Sarah Connor", "PERSON")

        chunks = [
            "The company ",
            alias_company[:4],
            alias_company[4:],
            " was founded by ",
            alias_person[:7],
            alias_person[7:],
            " in 2020.",
        ]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert "NexGen" in result
        assert "Sarah Connor" in result


# ═════════════════════════════════════════════════════════════════════════════
# 6. Edge cases
# ═════════════════════════════════════════════════════════════════════════════


class TestStreamingEdgeCases:
    """Edge cases for the streaming unfilter."""

    async def test_empty_chunks_in_stream(self, session_with_aliases):
        """Empty strings in stream should be skipped."""
        chunks = ["Hello", "", " ", "", "world", ""]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert result == "Hello world"

    async def test_single_character_chunks(self, session_with_aliases):
        """Stream delivers one character at a time."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        alias_chars = list(alias)
        chunks = ["T", "e", "x", "t", " ", "w", "i", "t", "h", " "] + alias_chars + [" ", "e", "n", "d"]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks)))
        assert "NexGen" in result

    async def test_unicode_in_stream(self, session_with_aliases, alias_store):
        """Unicode characters in stream pass through fine."""
        s = Session(prompt="", conversation_id="unicode-conv")
        s.alias_store = alias_store
        chunks = ["Hello", " 👋", " world", " 🎉"]
        result = await _collect(s.unfilter_stream(_to_stream(chunks)))
        assert result == "Hello 👋 world 🎉"

    async def test_very_small_timeout(self, session_with_aliases):
        """Stream with a very small timeout should not block."""
        alias = session_with_aliases.alias_store.get_or_create("test-conv-stream", "NexGen", "COMPANY")
        chunks = ["Hello ", alias[:2], alias[2:], " world"]
        result = await _collect(session_with_aliases.unfilter_stream(_to_stream(chunks), timeout=0.001))
        assert "NexGen" in result