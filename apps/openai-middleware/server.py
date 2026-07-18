"""PIIFilter OpenAI Middleware — Drop-in proxy for any OpenAI-compatible client.

Set base_url=http://localhost:8080 and get prompt protection with zero code changes.

Run: uvicorn server:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import os
import logging
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="PIIFilter OpenAI Proxy")

# Configure the REAL OpenAI endpoint to forward to
REAL_OPENAI_URL = os.environ.get("PII_OPENAI_ENDPOINT", "https://api.openai.com/v1")
REAL_OPENAI_KEY = os.environ.get("PII_OPENAI_API_KEY", "")
PIIFILTER_MODE = os.environ.get("PII_MODE", "semantic")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "gpt-3.5-turbo"
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    """OpenAI-compatible /v1/chat/completions endpoint.

    Intercepts the request, filters the last user message through PIIFilter,
    then forwards to the real OpenAI endpoint and returns the response.
    """
    # Extract the last user message
    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user messages found")

    last_user_msg = user_messages[-1]
    original_prompt = last_user_msg.content

    # Filter through PIIFilter
    try:
        from piifilter_sdk import PIIFilter

        async with PIIFilter() as pii:
            result = await pii.filter(original_prompt, mode=PIIFILTER_MODE)
    except ImportError:
        logger.warning("PIIFilter SDK not installed — passing through without filtering")
        result = {"filtered": original_prompt, "blocked": False}
    except Exception as e:
        logger.error("PIIFilter error: %s — passing through original prompt", e)
        result = {"filtered": original_prompt, "blocked": False}

    if result.get("blocked"):
        return JSONResponse(
            content={
                "error": {
                    "message": f"PIIFilter blocked this prompt: {result.get('block_reason', 'Policy violation')}",
                    "type": "piifilter_block",
                }
            },
            status_code=400,
        )

    filtered_prompt = result["filtered"]
    entities = result.get("entities", [])

    # Rebuild messages with filtered content
    filtered_messages = []
    for m in req.messages:
        if m.role == "user" and m.content == original_prompt:
            filtered_messages.append({"role": "user", "content": filtered_prompt})
        else:
            filtered_messages.append({"role": m.role, "content": m.content})

    # Forward to real OpenAI
    headers = {"Content-Type": "application/json"}
    if REAL_OPENAI_KEY:
        headers["Authorization"] = f"Bearer {REAL_OPENAI_KEY}"

    forward_url = f"{REAL_OPENAI_URL.rstrip('/')}/chat/completions"
    forward_payload = req.model_dump()
    forward_payload["messages"] = filtered_messages

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if req.stream:
                # Streaming response
                response = await client.post(forward_url, json=forward_payload, headers=headers)
                return StreamingResponse(
                    response.iter_raw(),
                    media_type="text/event-stream",
                    headers={
                        "X-PIIFilter-Entities": str(len(entities)),
                        "X-PIIFilter-Active": "true",
                    },
                )
            else:
                response = await client.post(forward_url, json=forward_payload, headers=headers)
                response.raise_for_status()
                data = response.json()

        # Add PIIFilter metadata headers
        resp = JSONResponse(content=data)
        resp.headers["X-PIIFilter-Entities"] = str(len(entities))
        resp.headers["X-PIIFilter-Active"] = "true"
        if entities:
            types = list(set(e.get("type", "?") for e in entities))
            resp.headers["X-PIIFilter-Types"] = ",".join(types)
        return resp

    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail=f"Cannot reach OpenAI endpoint at {REAL_OPENAI_URL}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenAI endpoint timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"OpenAI returned error: {e.response.text}")


@app.get("/v1/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "piifilter-openai-proxy"}


@app.get("/")
async def root():
    return {
        "service": "PIIFilter OpenAI Middleware",
        "version": "2.0.0",
        "endpoints": {
            "POST /v1/chat/completions": "Forward filtered prompts to OpenAI",
            "GET /v1/health": "Health check",
        },
        "configuration": {
            "PII_OPENAI_ENDPOINT": REAL_OPENAI_URL,
            "PII_MODE": PIIFILTER_MODE,
        },
    }