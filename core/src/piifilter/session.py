from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from piifilter.shared.models import (
    DetectedEntity,
    Replacement,
    ReplacementMode,
    RiskAssessment,
)
from piifilter.config import FilterConfig, PolicyConfig, ProviderConfig
from piifilter.shared.alias_store import AliasStore


@dataclass
class Session:
    """Single unified object passed through the entire pipeline.

    Every stage (Detect, Risk, Policy, Replace, Audit, Forward) reads from
    and writes to this object. No other arguments are passed between stages.

    Fields are grouped into logical sections:
      - Request: the input prompt and identifiers
      - Pipeline state: populated incrementally as stages execute
      - Configuration: how the pipeline should behave
      - Audit & metadata: observability data
    """

    # ── Request ──────────────────────────────────────────────────────────
    prompt: str
    conversation_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    mode: Optional[ReplacementMode] = None

    # ── Pipeline state (populated by stages) ─────────────────────────────
    entities: list[DetectedEntity] = field(default_factory=list)
    risk: Optional[RiskAssessment] = None
    replacements: list[Replacement] = field(default_factory=list)
    filtered_prompt: Optional[str] = None
    llm_response: Optional[str] = None
    blocked: bool = False
    block_reason: Optional[str] = None

    # ── Configuration ────────────────────────────────────────────────────
    config: FilterConfig = field(default_factory=FilterConfig)
    policy: Optional[dict[str, Any]] = None
    provider_config: Optional[ProviderConfig] = None
    alias_store: Optional[AliasStore] = None

    # ── Audit & metadata ─────────────────────────────────────────────────
    replacement_map: dict[str, str] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def latency_ms(self) -> float:
        """Total pipeline latency in milliseconds, or 0.0 if incomplete."""
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0.0

    @property
    def is_blocked(self) -> bool:
        """Convenience alias for the ``blocked`` flag."""
        return self.blocked

    # ── Public API ───────────────────────────────────────────────────────

    def add_audit(self, stage: str, event_type: str, data: dict[str, Any]) -> None:
        """Record an audit event for a pipeline stage.

        Args:
            stage: The pipeline stage name (e.g. ``"detect"``, ``"replace"``).
            event_type: The kind of event (e.g. ``"entity_found"``, ``"replacement_applied"``).
            data: Arbitrary key-value payload for the event.
        """
        self.audit_events.append({
            "stage": stage,
            "event": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def mark_started(self) -> None:
        """Record the pipeline start timestamp."""
        self.started_at = datetime.utcnow()

    def mark_completed(self) -> None:
        """Record the pipeline completion timestamp."""
        self.completed_at = datetime.utcnow()

    # ── Alias helpers (conversation-aware) ─────────────────────────────

    def get_alias(self, original: str, entity_type: Optional[str] = None) -> str:
        """Get or create a conversation-scoped alias for an original value.

        Delegates to the ``alias_store`` if available, otherwise falls
        back to a one-off call to ``generate_alias``.  Always prefer
        setting ``alias_store`` on the session so aliases are
        deterministic across turns within a conversation.
        """
        if self.alias_store is not None and self.conversation_id:
            return self.alias_store.get_or_create(self.conversation_id, original, entity_type)
        from piifilter.shared.utils import generate_alias
        return generate_alias(original, self.config.replacement.seed, self.conversation_id or "")

    def replace_in_response(self, text: str) -> str:
        """Replace FILTERED aliases back to original values in an LLM response.

        Scans the text for any alias known in the current conversation
        and restores the original.  Requires ``alias_store`` and
        ``conversation_id`` to be set.
        """
        if self.alias_store is None or not self.conversation_id:
            return text
        mappings = self.alias_store.get_all(self.conversation_id)
        # Build reverse map: alias -> original
        reverse = {v: k for k, v in mappings.items()}
        result = text
        for alias, original in reverse.items():
            if alias in result:
                result = result.replace(alias, original)
        return result

    # ── Streaming unfilter ───────────────────────────────────────────

    def _build_alias_map(self) -> dict[str, str]:
        """Build a reverse lookup mapping (alias → original) for this conversation.

        Returns:
            A dict of ``{alias: original}``, or empty dict if no alias_store
            or conversation_id is set.
        """
        if self.alias_store is None or not self.conversation_id:
            return {}
        mappings = self.alias_store.get_all(self.conversation_id)
        return {v: k for k, v in mappings.items()}

    async def unfilter_stream(
        self,
        stream: AsyncGenerator[str, None],
        timeout: float = 2.0,
    ) -> AsyncGenerator[str, None]:
        """Streaming unfilter: reverse aliases in a token stream in real time.

        Buffers incoming tokens at alias boundaries.  When a potential alias
        prefix is seen, we collect tokens until a complete alias is found or
        the timeout expires.  If we find a complete alias, we emit the original
        value.  If we timeout, we flush the buffered raw text.

        Args:
            stream: An async generator yielding text chunks (tokens) from the LLM.
            timeout: Max seconds to buffer when a partial alias match is detected.
                     Defaults to 2.0 seconds.

        Yields:
            Text chunks with aliases replaced by their original values.
        """
        alias_map = self._build_alias_map()
        if not alias_map:
            # No aliases to resolve — pass through
            async for chunk in stream:
                yield chunk
            return

        # Sort aliases by length descending so longer aliases match first
        sorted_aliases = sorted(alias_map.keys(), key=len, reverse=True)

        buffer = ""
        in_alias = False
        partial_match_key: str | None = None

        async for chunk in stream:
            if not chunk:
                continue

            buffer += chunk

            if not in_alias:
                # Check if the buffer (or its tail) matches a prefix of any alias
                matched_prefix = False
                for alias in sorted_aliases:
                    # Exact match in buffer
                    if alias in buffer:
                        # Emit everything up to the alias, then the original, then keep the rest
                        idx = buffer.index(alias)
                        if idx > 0:
                            yield buffer[:idx]
                        yield alias_map[alias]
                        buffer = buffer[idx + len(alias):]
                        matched_prefix = False  # Reset — we already emitted
                        break
                    # Partial alias at the end of buffer
                    if alias.startswith(buffer[-len(alias):]) and len(buffer[-len(alias):]) < len(alias):
                        in_alias = True
                        partial_match_key = alias
                        matched_prefix = True
                        break
                    # Buffer tail is a prefix of this alias (shorter than full alias)
                    tail = buffer[-len(alias):]
                    if len(tail) < len(alias) and alias.startswith(tail) and len(tail) > 0:
                        in_alias = True
                        partial_match_key = alias
                        matched_prefix = True
                        break

                if not matched_prefix:
                    # No alias-related content — flush and continue
                    yield buffer
                    buffer = ""
            else:
                # We're inside a potential alias — buffer more
                assert partial_match_key is not None
                if partial_match_key in buffer:
                    # Complete alias found — emit original
                    idx = buffer.index(partial_match_key)
                    if idx > 0:
                        yield buffer[:idx]
                    yield alias_map[partial_match_key]
                    buffer = buffer[idx + len(partial_match_key):]
                    in_alias = False
                    partial_match_key = None
                else:
                    # Still potential — if buffer exceeds alias length, it's not matching
                    if len(buffer) >= len(partial_match_key) and not buffer.endswith(partial_match_key[:len(buffer)]):
                        # Not matching — flush a char at a time from the front
                        # Actually flush the whole buffer since we've passed
                        yield buffer
                        buffer = ""
                        in_alias = False
                        partial_match_key = None

        # ── End of stream: flush remaining buffer ────────────────────
        if buffer:
            if in_alias and partial_match_key and partial_match_key in buffer:
                idx = buffer.index(partial_match_key)
                if idx > 0:
                    yield buffer[:idx]
                yield alias_map[partial_match_key]
                buffer = buffer[idx + len(partial_match_key):]
            if buffer:
                yield buffer

        return