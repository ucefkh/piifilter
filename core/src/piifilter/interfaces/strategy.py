from __future__ import annotations

from abc import ABC, abstractmethod


class ReplacementStrategy(ABC):
    """Abstract interface for PII replacement strategies (redact, mask, fake, etc)."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def apply(self, text: str, detections: list[dict]) -> str:
        """Apply replacement strategy to detected PII in text."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...