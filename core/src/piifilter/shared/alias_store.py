"""Conversation-scoped alias store for deterministic, reversible PII replacement."""

from __future__ import annotations

from typing import Optional

from piifilter.shared.alias_store_persistent import AliasBackend, MemoryAliasBackend
from piifilter.shared.utils import generate_alias


class AliasStore:
    """Thread-safe store for conversation-scoped aliases.

    For a given conversation_id, the same original value always maps
    to the same alias. This allows the LLM to build consistent context
    across multiple turns.

    The store delegates to an ``AliasBackend`` instance.  By default the
    backend is ``MemoryAliasBackend`` (in-memory, ephemeral).  Pass a
    ``SQLiteAliasBackend`` to persist across process restarts.

    The in-memory store remains the default.  The SQLite/encrypted store
    is opt-in via ``PIIFILTER_STORE_KEY`` env var (see
    :class:`~piifilter.shared.alias_store_persistent.SQLiteAliasBackend`).
    """

    def __init__(self, seed: str = "deterministic", backend: Optional[AliasBackend] = None):
        self._seed = seed
        self._backend = backend or MemoryAliasBackend(seed=seed)

    def get_or_create(self, conversation_id: str, original: str, entity_type: Optional[str] = None) -> str:
        """Return existing alias for this value in this conversation, or create one."""
        return self._backend.get_or_create(conversation_id, original, entity_type)

    def get_original(self, conversation_id: str, alias: str) -> Optional[str]:
        """Reverse-lookup: given an alias, return the original value."""
        return self._backend.get_original(conversation_id, alias)

    def get_all(self, conversation_id: str) -> dict[str, str]:
        """Get all {original: alias} mappings for a conversation."""
        return self._backend.get_all(conversation_id)

    def clear_conversation(self, conversation_id: str) -> None:
        """Remove all mappings for a conversation."""
        self._backend.clear_conversation(conversation_id)

    def clear_all(self) -> None:
        """Reset the entire store."""
        self._backend.clear_all()

    # ── Backend access ────────────────────────────────────────────

    @property
    def backend(self) -> AliasBackend:
        """The underlying backend instance (for testing / inspection)."""
        return self._backend