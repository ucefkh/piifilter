"""Conversation-scoped alias store for deterministic, reversible PII replacement."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Optional

from piifilter.shared.utils import generate_alias


class AliasStore:
    """Thread-safe store for conversation-scoped aliases.

    For a given conversation_id, the same original value always maps
    to the same alias. This allows the LLM to build consistent context
    across multiple turns.
    """

    def __init__(self, seed: str = "deterministic"):
        self._lock = threading.RLock()
        self._store: dict[str, dict[str, str]] = defaultdict(dict)  # conv_id -> {original: alias}
        self._reverse: dict[str, dict[str, str]] = defaultdict(dict)  # conv_id -> {alias: original}
        self._seed = seed

    def get_or_create(self, conversation_id: str, original: str, entity_type: Optional[str] = None) -> str:
        """Return existing alias for this value in this conversation, or create one."""
        with self._lock:
            conv = self._store[conversation_id]
            if original in conv:
                return conv[original]

            alias = generate_alias(original, self._seed, conversation_id)
            conv[original] = alias
            self._reverse[conversation_id][alias] = original
            return alias

    def get_original(self, conversation_id: str, alias: str) -> Optional[str]:
        """Reverse-lookup: given an alias, return the original value."""
        with self._lock:
            return self._reverse.get(conversation_id, {}).get(alias)

    def get_all(self, conversation_id: str) -> dict[str, str]:
        """Get all {original: alias} mappings for a conversation."""
        with self._lock:
            return dict(self._store.get(conversation_id, {}))

    def clear_conversation(self, conversation_id: str) -> None:
        """Remove all mappings for a conversation."""
        with self._lock:
            self._store.pop(conversation_id, None)
            self._reverse.pop(conversation_id, None)

    def clear_all(self) -> None:
        """Reset the entire store."""
        with self._lock:
            self._store.clear()
            self._reverse.clear()

    @property
    def conversation_count(self) -> int:
        with self._lock:
            return len(self._store)

    @property
    def total_mappings(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._store.values())