"""LM Studio provider implementation — connects to real LLMs.

Backend auto-detection on startup:
1. LM Studio at ``http://localhost:1234/v1`` (OpenAI-compatible)
2. Ollama at ``http://localhost:11434/v1`` (OpenAI-compatible since 0.5.0)
3. Falls back to any explicitly configured ``endpoint``

The provider makes real ``POST /chat/completions`` calls with ``httpx.AsyncClient``.
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Any

import httpx

from piifilter.interfaces.provider import Provider, ProviderCapabilities

if TYPE_CHECKING:
    from piifilter.session import Session

logger = getLogger(__name__)

LM_STUDIO_ENDPOINT = "http://localhost:1234/v1"
OLLAMA_ENDPOINT = "http://localhost:11434/v1"
DEFAULT_MODEL = "local-model"


class LMStudioProvider(Provider):
    """Provider implementation for local LLM backends (OpenAI-compatible).

    Auto-detects available backends on initialization in this order:
        1. LM Studio (http://localhost:1234/v1)
        2. Ollama (http://localhost:11434/v1)
        3. Falls back to the configured endpoint

    Uses ``n_ctx=4096`` for initial model listing and ``timeout=300s``
    for chat completions.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._detected_endpoint: str | None = None
        self._detected_model: str | None = None
        self._endpoint: str = LM_STUDIO_ENDPOINT
        self._model: str = DEFAULT_MODEL

    # ── Provider interface ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "lmstudio"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def initialize(self) -> None:
        timeout = httpx.Timeout(10.0)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))

        # Try LM Studio first, then Ollama
        candidates = [
            ("LM Studio", LM_STUDIO_ENDPOINT),
            ("Ollama", OLLAMA_ENDPOINT),
        ]
        for label, ep in candidates:
            models = await self._fetch_models(ep)
            if models:
                self._detected_endpoint = ep
                self._detected_model = models[0]
                self._endpoint = ep
                self._model = models[0]
                logger.info(
                    "Detected %s at %s — using model '%s'",
                    label, ep, models[0],
                )
                return

        # No local backend found — use configured endpoint as-is
        logger.info(
            "No local LLM backend detected (LM Studio / Ollama). "
            "Will use configured endpoint: %s",
            self._endpoint,
        )

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def forward(self, session: Session) -> str:
        if self._client is None:
            raise RuntimeError("LMStudioProvider not initialized — call initialize() first")

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
            msg = f"[PIIFilter Error: LLM returned {exc.response.status_code}]"
            logger.warning("LLM HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return msg
        except httpx.RequestError as exc:
            msg = f"[PIIFilter Error: LLM request failed — {exc}]"
            logger.warning("LLM request error: %s", exc)
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

    async def _fetch_models(
        self,
        endpoint: str,
    ) -> list[str]:
        """Fetch model IDs from an OpenAI-compatible ``/models`` endpoint.

        Returns an empty list if the endpoint is unreachable or returns
        no usable models.
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as c:
                resp = await c.get(f"{endpoint}/models")
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        # OpenAI-compatible: {"data": [{"id": "model-name", ...}, ...]}
        raw = data.get("data") or data.get("models") or []
        if isinstance(raw, list):
            models = []
            for item in raw:
                if isinstance(item, dict):
                    mid = item.get("id") or item.get("name") or item.get("model")
                    if mid:
                        models.append(str(mid))
            return models

        # Ollama API: {"models": [{"name": "model-name", ...}, ...]}
        return []

    def _resolve_config(self, session: Session) -> None:
        """Read endpoint and model from session config, preferring provider_config.

        Preserves any auto-detected endpoint/model that was found during
        ``initialize()`` — only overrides when the session config provides
        a *non-default* value.
        """
        if session.provider_config is not None:
            cfg = session.provider_config
            if cfg.endpoint and cfg.endpoint != LM_STUDIO_ENDPOINT:
                self._endpoint = cfg.endpoint
            if cfg.default_model and cfg.default_model != DEFAULT_MODEL:
                self._model = cfg.default_model
        else:
            provider_cfg = session.config.provider
            if provider_cfg.default_model and provider_cfg.default_model != DEFAULT_MODEL:
                self._model = provider_cfg.default_model
            if provider_cfg.endpoint and provider_cfg.endpoint != LM_STUDIO_ENDPOINT:
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
            logger.warning("Unexpected LLM response: %s", str(data)[:300])
            return "[PIIFilter Error: unexpected LLM response format]"