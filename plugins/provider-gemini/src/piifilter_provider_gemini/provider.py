"""Gemini provider implementation.

Connects to ``https://generativelanguage.googleapis.com/v1beta`` and
forwards filtered prompts as ``/models/{model}:generateContent`` requests
using the Gemini API format.  Auth is via ``x-goog-api-key`` header.
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Any

import httpx

from piifilter.interfaces.provider import Provider, ProviderCapabilities

if TYPE_CHECKING:
    from piifilter.session import Session

logger = getLogger(__name__)

DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(Provider):
    """Provider implementation for Google Gemini's generateContent API."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._endpoint = DEFAULT_ENDPOINT
        self._api_key: str = ""
        self._model = DEFAULT_MODEL

    # ── Provider interface ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_images=True,
        )

    async def initialize(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def forward(self, session: Session) -> str:
        if self._client is None:
            raise RuntimeError("GeminiProvider not initialized — call initialize() first")

        prompt = session.filtered_prompt
        if not prompt:
            return ""

        self._resolve_config(session)

        body = self._build_body(session, prompt)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        try:
            response = await self._client.post(
                f"{self._endpoint}/models/{self._model}:generateContent",
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return self._extract_text(data)
        except httpx.HTTPStatusError as exc:
            msg = f"[PIIFilter Error: Gemini API returned {exc.response.status_code}]"
            logger.warning("Gemini HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return msg
        except httpx.RequestError as exc:
            msg = f"[PIIFilter Error: Gemini request failed — {exc}]"
            logger.warning("Gemini request error: %s", exc)
            return msg

    async def check_health(self) -> bool:
        if self._client is None or not self._api_key:
            return False
        try:
            resp = await self._client.get(
                f"{self._endpoint}/models",
                headers={"x-goog-api-key": self._api_key},
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
        """Build a Gemini ``generateContent`` request body."""
        contents: list[dict[str, Any]] = [
            {"parts": [{"text": prompt}], "role": "user"},
        ]

        # Prepend prior messages if available
        if session.metadata.get("messages"):
            for msg in session.metadata["messages"]:
                role = "model" if msg.get("role") == "assistant" else "user"
                contents.insert(0, {"parts": [{"text": msg["content"]}], "role": role})

        body: dict[str, Any] = {
            "contents": contents,
        }

        # Safety settings — moderate by default
        harm_categories = [
            "HARM_CATEGORY_HARASSMENT",
            "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "HARM_CATEGORY_DANGEROUS_CONTENT",
        ]
        body["safetySettings"] = [
            {"category": cat, "threshold": "BLOCK_ONLY_HIGH"}
            for cat in harm_categories
        ]

        # Generation config
        gen_config: dict[str, Any] = {}
        if "temperature" in session.metadata:
            gen_config["temperature"] = session.metadata["temperature"]
        if "max_tokens" in session.metadata:
            gen_config["maxOutputTokens"] = session.metadata["max_tokens"]
        if gen_config:
            body["generationConfig"] = gen_config

        return body

    def _extract_text(self, data: dict[str, Any]) -> str:
        """Pull response text from a Gemini generateContent response."""
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                # Check for blocked / safety reason
                prompt_feedback = data.get("promptFeedback", {})
                if prompt_feedback.get("blockReason"):
                    return (
                        f"[PIIFilter Info: Gemini blocked — "
                        f"{prompt_feedback['blockReason']}]"
                    )
                return "[PIIFilter Info: Gemini returned no candidates]"

            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [p["text"] for p in parts if "text" in p]
            return "\n".join(texts) if texts else ""
        except (KeyError, IndexError, TypeError):
            logger.warning("Unexpected Gemini response: %s", str(data)[:300])
            return "[PIIFilter Error: unexpected Gemini response format]"