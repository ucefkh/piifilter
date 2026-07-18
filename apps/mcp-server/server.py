"""PIIFilter MCP Server — Claude Desktop protection.

Run: uv run python server.py
Or:  mcp run server.py
"""

from __future__ import annotations

import json
import sys
from typing import Optional

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


def create_server() -> Optional[object]:
    """Create and return the MCP server. Returns None if mcp not installed."""
    if not MCP_AVAILABLE:
        return None

    server = Server("piifilter")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="filter_prompt",
                description="Detect and replace PII in a prompt before sending to an LLM",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "The prompt text to filter",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["semantic", "mask", "generalize"],
                            "description": "Replacement mode (default: semantic)",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Optional conversation ID for consistent aliases",
                        },
                    },
                    "required": ["prompt"],
                },
            ),
            Tool(
                name="scan_prompt",
                description="Scan a prompt for PII without modifying it",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The prompt to scan"},
                    },
                    "required": ["prompt"],
                },
            ),
            Tool(
                name="check_health",
                description="Check if the PIIFilter server is healthy",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            from piifilter_sdk import PIIFilter

            async with PIIFilter() as pii:
                if name == "filter_prompt":
                    prompt = arguments["prompt"]
                    mode = arguments.get("mode", "semantic")
                    conv_id = arguments.get("conversation_id")
                    result = await pii.filter(prompt, mode=mode, conversation_id=conv_id)

                    if result.get("blocked"):
                        text = f"[BLOCKED] {result['block_reason']}"
                    else:
                        entities = result.get("entities", [])
                        risk = result.get("risk", {})
                        text = (
                            f"Filtered prompt:\n{result['filtered']}\n\n"
                            f"---\n"
                            f"Risk: {risk.get('score', 0):.0f}/100 ({risk.get('level', 'unknown')}) | "
                            f"Entities: {len(entities)} | "
                            f"Latency: {result.get('latency_ms', 0):.1f}ms"
                        )
                    return [TextContent(type="text", text=text)]

                elif name == "scan_prompt":
                    prompt = arguments["prompt"]
                    result = await pii.scan(prompt)
                    entities = result.get("entities", [])
                    risk = result.get("risk", {})
                    lines = [f"Entities detected: {len(entities)}"]
                    for e in entities:
                        lines.append(f"  - {e.get('type', '?')}: '{e.get('text', '')[:50]}' (confidence: {e.get('score', 0):.2f})")
                    lines.append(f"\nRisk: {risk.get('score', 0):.0f}/100 ({risk.get('level', 'unknown')})")
                    return [TextContent(type="text", text="\n".join(lines))]

                elif name == "check_health":
                    return [TextContent(type="text", text="PIIFilter MCP server is running")]

        except ImportError as e:
            return [TextContent(type="text", text=f"PIIFilter SDK not available: {e}")]
        except Exception as e:
            return [TextContent(type="text", text=f"PIIFilter error: {e}")]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


def main():
    server = create_server()
    if server is None:
        print("PIIFilter MCP requires `mcp` package. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    import anyio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()