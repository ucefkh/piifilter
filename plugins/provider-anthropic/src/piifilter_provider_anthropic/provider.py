"""Anthropic provider implementation.

Connects to ``https://api.anthropic.com/v1`` and forwards filtered prompts
as ``/messages`` requests using the Anthropic message format.
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Any

import httpx

from piifilter.interfaces.provider import Provider, ProviderCapabilities

if TYPE_CHECKING:
    from piifilter.session import Session

logger = getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(Provider):
    """Provider implementation for Anthropic's Messages API."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._endpoint = DEFAULT_ENDPOINT
        self._api_key: str = ""
        self._model = DEFAULT_MODEL

    # ── Provider interface ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_reasoning=True,
        )

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def forward(self, session: Session) -> str:
        if self._client is None:
            raise RuntimeError("AnthropicProvider not initialized — call initialize() first")

        prompt = session.filtered_prompt
        if not prompt:
            return ""

        self._resolve_config(session)

        body = self._build_body(session, prompt)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": self._api_key,
        }

        try:
            response = await self._client.post(
                f"{self._endpoint}/messages",
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return self._extract_text(data)
        except httpx.HTTPStatusError as exc:
            msg = f"[PIIFilter Error: Anthropic API returned {exc.response.status_code}]"
            logger.warning("Anthropic HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return msg
        except httpx.RequestError as exc:
            msg = f"[PIIFilter Error: Anthropic request failed — {exc}]"
            logger.warning("Anthropic request error: %s", exc)
            return msg

    async def check_health(self) -> bool:
        if self._client is None or not self._api_key:
            return False
        try:
            resp = await self._client.get(
                f"{self._endpoint}/models",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            return resp.is_success
        except Exception:
            return False

    # ── Internals ───────────────────────────────────────────────────

    def _resolve_config(self, session: Session) -> None:
        """Read API key and model from session config, preferring provider_config."""
        if session.provider_config is not None:
            cfg = session.provider_config
            if cfg.api_key:
                self._api_key = cfg.api_key
            if cfg.endpoint and cfg.endpoint != DEFAULT_ENDPOINT:
                self._endpoint = cfg.endpoint
            if cfg.default_model:
                self._model = cfg.default_model
        else:
            provider_cfg = session.config.provider
            if provider_cfg.api_key:
                self._api_key = provider_cfg.api_key
            if provider_cfg.default_model:
                self._model = provider_cfg.default_model

    def _build_body(self, session: Session, prompt: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

        # If the session carried prior messages, prepend them
        if session.metadata.get("messages"):
            messages = list(session.metadata["messages"]) + messages

        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": session.metadata.get("max_tokens", 4096),
            "messages": messages,
        }

        if session.metadata.get("stream"):
            body["stream"] = True

        # Map reasoning effort if present
        reasoning = session.metadata.get("reasoning")
        if reasoning:
            body["thinking"] = {"type": "enabled", "budget_tokens": 2048}

        return body

    def _extract_text(self, data: dict[str, Any]) -> str:
        """Pull response text from an Anthropic messages response."""
        try:
            content_blocks = data["content"]
            parts: list[str] = []
            for block in content_blocks:
                if block.get("type") == "text":
                    parts.append(block["text"])
            return "\n".join(parts)
        except (KeyError, IndexError, TypeError):
            logger.warning("Unexpected Anthropic response structure: %s", str(data)[:300])
            return "[PIIFilter Error: unexpected Anthropic response format]"