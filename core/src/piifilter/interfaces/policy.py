from __future__ import annotations

from abc import ABC, abstractmethod


class PolicyEngine(ABC):
    """Abstract interface for policy engines that decide what to do with detections."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def evaluate(self, detections: list[dict], context: dict | None = None) -> list[dict]:
        """Evaluate detections against policy rules. Returns annotated detections with actions."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...