from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from piifilter.interfaces.plugin import Plugin

from .bus import EventBus, EventHandler, PipelineEvent

if TYPE_CHECKING:
    from piifilter.session import Session

logger = logging.getLogger(__name__)


class AuditTrailPlugin(Plugin):
    """Plugin that subscribes to all :class:`PipelineEvent` values and
    records a metadata-only audit trail on the session.

    Each audit entry contains:
    - ``event`` — the event name
    - ``timestamp`` — Unix timestamp (float, seconds)
    - ``request_id`` — the session request identifier

    **No prompt content is ever written to the audit trail.**
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._subscribed: bool = False
        self._handler: EventHandler = self._on_event

    @property
    def name(self) -> str:
        return "audit_trail"

    @property
    def version(self) -> str:
        return "1.0.0"

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": "Records a metadata-only audit trail of all pipeline events on the session",
        }

    async def initialize(self) -> None:
        """Subscribe to every known event."""
        if self._subscribed:
            return
        for event in PipelineEvent:
            self._event_bus.subscribe(event, self._handler)
        self._subscribed = True
        logger.info("AuditTrailPlugin subscribed to all %d events", len(PipelineEvent))

    async def shutdown(self) -> None:
        """Unsubscribe from all events."""
        if not self._subscribed:
            return
        for event in PipelineEvent:
            self._event_bus.unsubscribe(event, self._handler)
        self._subscribed = False
        logger.info("AuditTrailPlugin unsubscribed from all events")

    async def _on_event(self, event: PipelineEvent, session: Session) -> None:
        """Record a metadata-only audit entry on the session."""
        entry: dict[str, Any] = {
            "event": event.value,
            "timestamp": time.time(),
            "request_id": session.request_id,
        }
        session.audit_events.append(entry)