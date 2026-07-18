from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MetricsProvider(ABC):
    """Abstract interface for metrics collection (counters, histograms, etc)."""

    @abstractmethod
    def increment(self, metric: str, tags: dict[str, str] | None = None, value: int = 1) -> None:
        ...

    @abstractmethod
    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        ...

    @abstractmethod
    def histogram(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        ...

    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...