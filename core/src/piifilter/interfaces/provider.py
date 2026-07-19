from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from piifilter.session import Session


@dataclass
class ProviderCapabilities:
    """Describes what a provider implementation supports."""

    supports_streaming: bool = False
    supports_images: bool = False
    supports_tools: bool = False
    supports_json: bool = False
    supports_reasoning: bool = False


class Provider(ABC):
    """Abstract interface for LLM providers.

    Implementations wrap a specific LLM API (OpenAI, Anthropic, Gemini,
    local models, etc.) and handle auth, request formatting, and error
    mapping so the rest of the pipeline is provider-agnostic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Perform any one-time async setup (e.g. create client pool)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Release provider resources (close client, free connections)."""
        ...

    @abstractmethod
    async def forward(self, session: Session) -> str:
        """Send ``session.filtered_prompt`` to the LLM and return the response.

        Args:
            session: The pipeline session carrying the filtered prompt and
                     provider configuration.

        Returns:
            The raw text response from the LLM.

        Raises:
            ProviderError: On any transport or API error.
        """
        ...

    async def forward_stream(self, session: Session) -> AsyncGenerator[str, None]:
        """Stream the filtered prompt to the LLM, yielding chunks.

        The default implementation calls ``forward()`` and yields the full
        response as a single chunk.  Providers that support native streaming
        should override this to yield token-by-token.

        Args:
            session: The pipeline session carrying the filtered prompt and
                     provider configuration.

        Yields:
            Text chunks from the LLM response.
        """
        response = await self.forward(session)
        yield response

    @abstractmethod
    async def check_health(self) -> bool:
        """Quick health check against the provider endpoint.

        Returns:
            ``True`` if the endpoint is reachable and responsive.
        """
        ...