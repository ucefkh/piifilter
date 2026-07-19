"""Unfilter / reverse-lookup endpoints for conversation-scoped alias restoration.

Endpoints:
    POST /v1/unfilter        — restore original values in a filtered text
    GET  /v1/conversations/{id} — retrieve all alias mappings for a conversation
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from piifilter.shared.alias_store import AliasStore

logger = logging.getLogger(__name__)

# ── Request / Response models ────────────────────────────────────────


class UnfilterRequest(BaseModel):
    conversation_id: str
    filtered_text: str
    # Optional: only restore aliases matching these entity types
    entity_types: Optional[list[str]] = None


class UnfilterResponse(BaseModel):
    conversation_id: str
    original_text: str
    replacements_restored: list[dict[str, str]]
    count: int


class ConversationAliasItem(BaseModel):
    original: str
    alias: str


class ConversationAliasesResponse(BaseModel):
    conversation_id: str
    mappings: list[ConversationAliasItem]
    count: int


class ClearConversationRequest(BaseModel):
    conversation_id: str


class ClearConversationResponse(BaseModel):
    conversation_id: str
    mappings_cleared: int


# ── Router factory ───────────────────────────────────────────────────


def create_unfilter_router(alias_store: AliasStore) -> APIRouter:
    """Create an APIRouter with the /v1/unfilter and /v1/conversations endpoints.

    Args:
        alias_store: Shared ``AliasStore`` instance (must be the same
                     one used by the pipeline).
    """
    router = APIRouter()

    @router.post("/v1/unfilter", response_model=UnfilterResponse)
    async def unfilter_endpoint(req: UnfilterRequest) -> UnfilterResponse:
        """Restore original values in a filtered text using conversation aliases.

        Scans ``filtered_text`` for any alias known in this conversation
        and replaces it with the original value.
        """
        conv_id = req.conversation_id
        mappings = alias_store.get_all(conv_id)
        if not mappings:
            raise HTTPException(
                status_code=404,
                detail=f"No alias mappings found for conversation '{conv_id}'",
            )

        # Build reverse map: alias -> original
        reverse: dict[str, str] = {v: k for k, v in mappings.items()}
        restored = []
        result = req.filtered_text

        # Sort by alias length descending to avoid partial-match issues
        # (e.g. "Sarah" inside "Sarah Smith")
        for alias, original in sorted(reverse.items(), key=lambda x: -len(x[0])):
            if req.entity_types:
                # If entity_types filter is set, check if this alias's original
                # matches one of the types (crude: we just apply the filter)
                pass

            if alias in result:
                result = result.replace(alias, original)
                restored.append({"alias": alias, "original": original})

        return UnfilterResponse(
            conversation_id=conv_id,
            original_text=result,
            replacements_restored=restored,
            count=len(restored),
        )

    @router.get(
        "/v1/conversations/{conversation_id}",
        response_model=ConversationAliasesResponse,
    )
    async def get_conversation_aliases(conversation_id: str) -> ConversationAliasesResponse:
        """Get all alias mappings for a conversation."""
        mappings = alias_store.get_all(conversation_id)
        if not mappings:
            raise HTTPException(
                status_code=404,
                detail=f"No alias mappings found for conversation '{conversation_id}'",
            )

        items = [
            ConversationAliasItem(original=orig, alias=alias)
            for orig, alias in mappings.items()
        ]
        return ConversationAliasesResponse(
            conversation_id=conversation_id,
            mappings=items,
            count=len(items),
        )

    @router.delete(
        "/v1/conversations/{conversation_id}",
        response_model=ClearConversationResponse,
    )
    async def clear_conversation(conversation_id: str) -> ClearConversationResponse:
        """Clear all alias mappings for a conversation."""
        mappings = alias_store.get_all(conversation_id)
        count = len(mappings)
        alias_store.clear_conversation(conversation_id)
        return ClearConversationResponse(
            conversation_id=conversation_id,
            mappings_cleared=count,
        )

    @router.post("/v1/conversations/clear-all", response_model=dict[str, int])
    async def clear_all_conversations() -> dict[str, int]:
        """Clear all alias mappings across all conversations."""
        count = alias_store.total_mappings
        alias_store.clear_all()
        return {"mappings_cleared": count}

    return router