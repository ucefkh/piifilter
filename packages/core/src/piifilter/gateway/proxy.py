"""LLM Gateway proxy — forwards sanitised prompts to configured LLM providers.

Privacy-first design:
- Never logs prompt content.
- Sanitised text arrives from the PIIFilter; this module only forwards it.
- Error messages are generic and expose no internal details.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from piifilter.config import FilterConfig
from piifilter.gateway.provider_map import get_provider_info

logger = logging.getLogger(__name__)

# Default timeout for all outbound LLM requests (seconds)
_REQUEST_TIMEOUT = 30


class LLMGateway:
    """Forwards already-filtered (sanitised) prompts to a configured LLM provider.

    The gateway does **not** perform any PII filtering itself — it only
    relays the prompt it receives to the backend LLM provider.
    """

    def __init__(self, config: FilterConfig) -> None:
        """Initialise the gateway with a :class:`FilterConfig`.

        Args:
            config: Application config containing the ``provider`` section
                    with endpoint, api_key, and default_model settings.

        """
        self.config = config
        provider_cfg = config.provider

        # Resolve endpoint — prefer the config value, else fall back to
        # the known provider map, else default to LM Studio.
        provider_info = get_provider_info(provider_cfg.name)
        self._endpoint: str = (
            provider_cfg.endpoint
            or provider_info.get("endpoint", "http://localhost:1234/v1")
        )
        self._format: str = provider_info.get("format", "openai")
        self._api_key: str = provider_cfg.api_key
        self._default_model: str = provider_cfg.default_model

        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

    async def forward(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Send the (already filtered) prompt to the LLM provider.

        Args:
            prompt: The sanitised text to forward.
            model:  Optional model override. Falls back to
                    ``config.provider.default_model``.

        Returns:
            The LLM response text, or an error placeholder string if the
            request fails.

        """
        selected_model = model or self._default_model

        try:
            if self._format == "anthropic":
                return await self._forward_anthropic(prompt, selected_model)
            elif self._format == "gemini":
                return await self._forward_gemini(prompt, selected_model)
            else:
                # Default: OpenAI-compatible format (OpenAI, LM Studio,
                # Ollama, vLLM, DeepSeek, etc.)
                return await self._forward_openai_compat(prompt, selected_model)
        except httpx.TimeoutException:
            logger.warning("LLM gateway timeout for %s", self._endpoint)
            return (
                f"[PIIFilter Gateway Error: Unable to reach LLM provider "
                f"at {self._endpoint}]"
            )
        except httpx.ConnectError:
            logger.warning("LLM gateway connection refused at %s", self._endpoint)
            return (
                f"[PIIFilter Gateway Error: Unable to reach LLM provider "
                f"at {self._endpoint}]"
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "LLM gateway HTTP %d from %s", exc.response.status_code, self._endpoint
            )
            return (
                f"[PIIFilter Gateway Error: Provider returned "
                f"{exc.response.status_code}]"
            )
        except Exception:
            logger.exception("LLM gateway unexpected error for %s", self._endpoint)
            return f"[PIIFilter Gateway Error: Unable to reach LLM provider at {self._endpoint}]"

    async def _forward_openai_compat(
        self,
        prompt: str,
        model: str,
    ) -> str:
        """Forward via the OpenAI-compatible ``/chat/completions`` schema."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        url = f"{self._endpoint.rstrip('/')}/chat/completions"
        headers = self._build_headers()

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices", [])
        if not choices:
            logger.warning("LLM gateway: empty choices from %s", self._endpoint)
            return "[PIIFilter Gateway Error: Provider returned empty response]"
        return choices[0].get("message", {}).get("content", "")

    async def _forward_anthropic(
        self,
        prompt: str,
        model: str,
    ) -> str:
        """Forward via the Anthropic ``/v1/messages`` schema."""
        payload = {
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        url = f"{self._endpoint.rstrip('/')}/messages"
        headers = self._build_headers()
        headers["anthropic-version"] = "2023-06-01"

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        content_blocks = data.get("content", [])
        if not content_blocks:
            logger.warning("LLM gateway: empty Anthropic response from %s", self._endpoint)
            return "[PIIFilter Gateway Error: Provider returned empty response]"
        # Anthropic returns a list of content blocks; concatenate text blocks.
        texts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        return "".join(texts)

    async def _forward_gemini(
        self,
        prompt: str,
        model: str,
    ) -> str:
        """Forward via the Gemini ``:generateContent`` schema."""
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }
        url = (
            f"{self._endpoint.rstrip('/')}/models/{model}:generateContent"
        )
        headers = self._build_headers()

        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("LLM gateway: empty Gemini response from %s", self._endpoint)
            return "[PIIFilter Gateway Error: Provider returned empty response]"

        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts]
        return "".join(texts)

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for the outgoing request.

        Auth header strategy:
        - OpenAI / Anthropic → ``Authorization: Bearer {api_key}``
        - Gemini → ``x-goog-api-key: {api_key}``
        - Local endpoints (LM Studio, Ollama) → no auth header unless
          an API key is explicitly configured.

        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }

        if self._format == "gemini":
            if self._api_key:
                headers["x-goog-api-key"] = self._api_key
        elif self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        return headers

    async def check_health(self) -> bool:
        """Check whether the configured LLM endpoint is reachable.

        Performs a simple GET to the base endpoint URL. Does **not**
        require a valid model or API key — it only checks connectivity.

        Returns:
            ``True`` if the endpoint is reachable, ``False`` otherwise.

        """
        try:
            response = await self._client.get(
                self._endpoint.rstrip("/") + "/",
                timeout=5.0,
            )
            return response.status_code < 500
        except Exception:
            return False

    async def close(self) -> None:
        """Release the underlying HTTP client session."""
        await self._client.aclose()