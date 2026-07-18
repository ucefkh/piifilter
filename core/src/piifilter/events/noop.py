from __future__ import annotations

from typing import TYPE_CHECKING

from .bus import EventBus, EventHandler, PipelineEvent

if TYPE_CHECKING:
    from piifilter.session import Session


class NoOpEventBus(EventBus):
    """No-operation event bus that discards every event.

    Use in production when no subscribers are needed — avoids the
    overhead of handler dispatch and :func:`asyncio.gather` entirely.
    All three public methods are no-ops.
    """

    def subscribe(self, event: PipelineEvent, handler: EventHandler) -> None:
        """No-op."""

    def unsubscribe(self, event: PipelineEvent, handler: EventHandler) -> None:
        """No-op."""

    async def emit(self, event: PipelineEvent, session: Session) -> None:
        """No-op."""