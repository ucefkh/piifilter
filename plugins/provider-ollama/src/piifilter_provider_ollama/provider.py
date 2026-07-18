"""Ollama provider implementation.

Connects to ``http://localhost:11434/v1`` and forwards filtered prompts
as ``/chat/completions`` requests  (OpenAI-compatible, no auth).
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Any

import httpx

from piifilter.interfaces.provider import Provider, ProviderCapabilities

if TYPE_CHECKING:
    from piifilter.session import Session

logger = getLogger(__name__)

DEFAULT_ENDPOINT = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"


class OllamaProvider(Provider):
    """Provider implementation for local Ollama (OpenAI-compatible)."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._endpoint = DEFAULT_ENDPOINT
        self._model = DEFAULT_MODEL

    # ── Provider interface ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def forward(self, session: Session) -> str:
        if self._client is None:
            raise RuntimeError("OllamaProvider not initialized — call initialize() first")

        prompt = session.filtered_prompt
        if not prompt:
            return ""

        self._resolve_config(session)

        body = self._build_body(session, prompt)

        try:
            response = await self._client.post(
                f"{self._endpoint}/chat/completions",
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            return self._extract_text(data)
        except httpx.HTTPStatusError as exc:
            msg = f"[PIIFilter Error: Ollama returned {exc.response.status_code}]"
            logger.warning("Ollama HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return msg
        except httpx.RequestError as exc:
            msg = f"[PIIFilter Error: Ollama request failed — {exc}]"
            logger.warning("Ollama request error: %s", exc)
            return msg

    async def check_health(self) -> bool:
        if self._client is None:
            return False
        try:
            resp = await self._client.get(f"{self._endpoint}/models")
            return resp.is_success
        except Exception:
            return False

    # ── Internals ───────────────────────────────────────────────────

    def _resolve_config(self, session: Session) -> None:
        """Read endpoint and model from session config, preferring provider_config."""
        if session.provider_config is not None:
            cfg = session.provider_config
            if cfg.endpoint and cfg.endpoint != DEFAULT_ENDPOINT:
                self._endpoint = cfg.endpoint
            if cfg.default_model:
                self._model = cfg.default_model
        else:
            provider_cfg = session.config.provider
            if provider_cfg.default_model:
                self._model = provider_cfg.default_model
            if provider_cfg.endpoint and provider_cfg.endpoint != DEFAULT_ENDPOINT:
                self._endpoint = provider_cfg.endpoint

    def _build_body(self, session: Session, prompt: str) -> dict[str, Any]:
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

        if session.metadata.get("messages"):
            messages = list(session.metadata["messages"]) + messages

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }

        if session.metadata.get("temperature"):
            body["temperature"] = session.metadata["temperature"]
        if session.metadata.get("max_tokens"):
            body["max_tokens"] = session.metadata["max_tokens"]

        return body

    def _extract_text(self, data: dict[str, Any]) -> str:
        """Pull response text from an OpenAI-compatible chat completion response."""
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            logger.warning("Unexpected Ollama response: %s", str(data)[:300])
            return "[PIIFilter Error: unexpected Ollama response format]"