from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Plugin(ABC):
    """Abstract interface for aggregator plugins that bundle multiple capabilities."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        ...

    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Return plugin metadata (version, author, dependencies, etc)."""
        ...