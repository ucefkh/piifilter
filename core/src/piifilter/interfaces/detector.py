from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Detector(ABC):
    """Abstract interface for PII detectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def detect(self, text: str, *, language: str | None = None) -> list[dict[str, Any]]:
        """Detect PII entities in text. Returns a list of detections with position, type, confidence."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Lifecycle: prepare resources (load models, connect services)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Lifecycle: release resources."""
        ...