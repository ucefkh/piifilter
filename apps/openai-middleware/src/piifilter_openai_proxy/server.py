"""PIIFilter OpenAI Middleware — transparent OpenAI-compatible proxy.

Mimics the OpenAI ``/v1/chat/completions`` endpoint.  Receives a request,
extracts the last user message, runs it through PIIFilter, then forwards
the filtered prompt to the real OpenAI API (or any OpenAI-compatible
endpoint) and returns the response in the original format.

Environment variables
---------------------
``OPENAI_API_KEY``
    API key for the upstream OpenAI-compatible endpoint.
``OPENAI_BASE_URL``
    Base URL for the upstream endpoint (default ``https://api.openai.com/v1``).
``PIIFILTER_CONFIG``
    Optional path to a PIIFilter YAML config file.
``PIIFILTER_MODE``
    Default replacement mode (default ``"semantic"``).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from piifilter_sdk import PIIFilter

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get(
    "OPENAI_BASE_URL",
    "https://api.openai.com/v1",
).rstrip("/")
PIIFILTER_MODE = os.environ.get("PIIFILTER_MODE", "semantic")
PIIFILTER_CONFIG = os.environ.get("PIIFILTER_CONFIG") or None

# Remove trailing /v1 if someone set it, we add it back explicitly
UPSTREAM_BASE = OPENAI_BASE_URL.replace("/v1", "")


# ── Request / Response models ────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[list[str]] = None


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


# ── FastAPI app ──────────────────────────────────────────────────────


app = FastAPI(
    title="PIIFilter OpenAI Proxy",
    version="2.0.0",
    description="Transparent middleware that filters PII from prompts "
    "before forwarding to the OpenAI API.",
)


def _extract_last_user_message(messages: list[ChatMessage]) -> tuple[Optional[str], list[ChatMessage]]:
    """Extract the last user message from the chat history.

    Returns:
        Tuple of (user_prompt, remaining_messages).  The last user
        message's content is replaced with ``[FILTERED]`` placeholder
        in the remaining list so token counts stay aligned.
    """
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            last_user_idx = i
            break

    if last_user_idx == -1:
        return None, messages

    prompt = messages[last_user_idx].content
    remaining = [ChatMessage(role=m.role, content=m.content) for m in messages]
    # Build filtered message list — replace original user message with filtered placeholder
    filtered_messages = [
        ChatMessage(role=m.role, content=m.content) if i != last_user_idx
        else ChatMessage(role=m.role, content="[FILTERED]")
        for i, m in enumerate(messages)
    ]
    return prompt, filtered_messages


def _build_upstream_messages(
    original_messages: list[ChatMessage],
    filtered_prompt: str,
    last_user_idx: int,
) -> list[dict[str, str]]:
    """Rebuild the message list replacing the last user message with the filtered prompt."""
    result = []
    for i, m in enumerate(original_messages):
        if i == last_user_idx:
            result.append({"role": m.role, "content": filtered_prompt})
        else:
            result.append({"role": m.role, "content": m.content})
    return result


# ── Streaming helpers ────────────────────────────────────────────────


def _rewrite_stream_chunk(
    chunk: dict[str, Any],
    original_prompt: str,
    filtered_prompt: str,
) -> dict[str, Any]:
    """Replace any references to the original prompt content in stream chunks.

    For most streaming responses the content delta flows through the
    ``choices[0].delta.content`` path, which doesn't contain the original
    prompt — so this is a no-op in practice.  We still apply the
    substitution defensively.
    """
    raw = json.dumps(chunk)
    raw = raw.replace(original_prompt, filtered_prompt)
    return json.loads(raw)


async def _stream_forward(
    client: httpx.AsyncClient,
    upstream_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    original_prompt: str,
    filtered_prompt: str,
) -> AsyncIterator[bytes]:
    """Forward streaming request, rewriting chunks inline."""
    async with client.stream(
        "POST",
        upstream_url,
        json=body,
        headers=headers,
    ) as upstream:
        async for line in upstream.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                yield b"data: [DONE]\n\n"
                return
            try:
                chunk = json.loads(data)
                chunk = _rewrite_stream_chunk(chunk, original_prompt, filtered_prompt)
                yield f"data: {json.dumps(chunk)}\n\n".encode()
            except json.JSONDecodeError:
                yield line.encode() + b"\n"


# ── Endpoints ────────────────────────────────────────────────────────


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, raw_request: Request) -> Response:
    """OpenAI-compatible chat completions endpoint with PII filtering.

    Extracts the last user message, runs it through PIIFilter, then
    forwards the filtered content to the upstream OpenAI API and returns
    the response.  Supports both streaming and non-streaming modes.
    """
    client_headers = dict(raw_request.headers)
    # ── Extract user prompt ──────────────────────────────────────
    user_prompt, _ = _extract_last_user_message(req.messages)
    if not user_prompt:
        raise HTTPException(status_code=400, detail="No user message found in request")

    # ── Filter through PIIFilter ────────────────────────────────
    async with PIIFilter(config_path=PIIFILTER_CONFIG) as pii:
        result: dict[str, Any] = await pii.filter(
            user_prompt,
            mode=PIIFILTER_MODE,
        )
        if result.get("blocked"):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "prompt_blocked",
                    "message": result.get("block_reason", "PII content blocked by policy"),
                    "request_id": result.get("request_id"),
                },
            )
        filtered_prompt = result.get("filtered", user_prompt)

    # ── Find last user message index for message rewriting ──────
    last_user_idx = -1
    for i in range(len(req.messages) - 1, -1, -1):
        if req.messages[i].role == "user":
            last_user_idx = i
            break

    # ── Build upstream request ──────────────────────────────────
    upstream_messages = _build_upstream_messages(
        req.messages, filtered_prompt, last_user_idx,
    )

    upstream_url = f"{UPSTREAM_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    upstream_body = {
        "model": req.model,
        "messages": upstream_messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "top_p": req.top_p,
        "frequency_penalty": req.frequency_penalty,
        "presence_penalty": req.presence_penalty,
    }
    if req.stop:
        upstream_body["stop"] = req.stop

    # ── Forward request ─────────────────────────────────────────
    async with httpx.AsyncClient(timeout=120.0) as client:
        if req.stream:
            # Streaming response — proxy chunks as they arrive
            return StreamingResponse(
                _stream_forward(
                    client,
                    upstream_url,
                    headers,
                    upstream_body,
                    user_prompt,
                    filtered_prompt,
                ),
                media_type="text/event-stream",
            )

        # Non-streaming response
        upstream_resp = await client.post(upstream_url, json=upstream_body, headers=headers)
        if upstream_resp.status_code != 200:
            logger.error(
                "Upstream API error: %s %s",
                upstream_resp.status_code,
                upstream_resp.text[:500],
            )
            raise HTTPException(
                status_code=upstream_resp.status_code,
                detail=upstream_resp.json() if upstream_resp.headers.get("content-type", "").startswith("application/json")
                else upstream_resp.text,
            )

        upstream_data = upstream_resp.json()
        # Replace any reference of filtered_prompt back? No — the response is clean.
        return Response(
            content=json.dumps(upstream_data),
            media_type="application/json",
            headers={
                "Content-Type": "application/json",
            },
        )


# ── Health check ─────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, Any]:
    """Simple health check — confirms the proxy is running."""
    return {
        "status": "ok",
        "service": "PIIFilter OpenAI Proxy",
        "version": "2.0.0",
    }


# ── App factory ──────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Return a configured FastAPI instance (useful for testing)."""
    return app


# ── Startup hook ─────────────────────────────────────────────────────


@app.on_event("startup")
async def startup() -> None:
    """Log configuration on startup."""
    upstream = f"{UPSTREAM_BASE}/v1/chat/completions"
    logger.info(
        "PIIFilter OpenAI Proxy starting — upstream=%s mode=%s",
        upstream,
        PIIFILTER_MODE,
    )
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set — upstream calls will fail!")