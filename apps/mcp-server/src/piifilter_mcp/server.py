"""PIIFilter MCP Server — Claude Desktop tool integration via FastMCP.

Usage
-----
    mcp run piifilter_mcp.server:server

Or directly::

    python -m piifilter_mcp.server

Registers one tool ``filter_prompt`` that delegates to
``piifilter_sdk.PIIFilter``.  No transport logic leaks into the core.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from piifilter_sdk import PIIFilter

logger = logging.getLogger(__name__)

# ── Create FastMCP server ────────────────────────────────────────────

server = FastMCP(
    "piifilter",
    instructions="PIIFilter — detect and redact sensitive information from prompts.",
)


# ── Tool: filter_prompt ──────────────────────────────────────────────


@server.tool(
    name="filter_prompt",
    description="Scan a user prompt for PII, replace sensitive content, and return the filtered result.",
)
async def filter_prompt(
    prompt: str,
    mode: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> str:
    """Run the PIIFilter pipeline on a user prompt.

    Detects PII, assesses risk, replaces sensitive content, and returns
    the filtered result.  If the prompt is blocked (high-risk PII found)
    the response starts with ``[BLOCKED]``.

    Args:
        prompt: The user prompt to filter for PII.
        mode: Replacement mode — ``"mask"``, ``"semantic"``,
            ``"generalize"``, or ``"policy"``.  Defaults to the SDK
            config value when omitted.
        conversation_id: Optional conversation identifier for audit
            correlation.

    Returns:
        The filtered prompt string, or a ``[BLOCKED]`` message if the
        content was blocked by pipeline policy.
    """
    async with PIIFilter() as pii:
        result: dict[str, Any] = await pii.filter(
            prompt,
            mode=mode,
            conversation_id=conversation_id,
        )
        if result.get("blocked"):
            reason = result.get("block_reason", "Blocked by pipeline policy")
            return f"[BLOCKED] {reason}"

        return result.get("filtered", prompt)


# ── CLI entry point ──────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server over stdio (Claude Desktop default transport)."""
    server.run(transport="stdio")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()