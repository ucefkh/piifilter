from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from piifilter.session import Session

logger = logging.getLogger(__name__)


class PipelineEvent(str, Enum):
    """All pipeline lifecycle events.

    Events are emitted before and after every pipeline stage so that
    plugins can subscribe without modifying core pipeline logic.
    """

    BEFORE_DETECTION = "before_detection"
    AFTER_DETECTION = "after_detection"
    BEFORE_RISK = "before_risk"
    AFTER_RISK = "after_risk"
    BEFORE_POLICY = "before_policy"
    AFTER_POLICY = "after_policy"
    BEFORE_REPLACEMENT = "before_replacement"
    AFTER_REPLACEMENT = "after_replacement"
    BEFORE_FORWARD = "before_forward"
    AFTER_FORWARD = "after_forward"
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    PIPELINE_ERROR = "pipeline_error"


EventHandler = Callable[["PipelineEvent", "Session"], Any]


class EventBus:
    """Simple async event bus.

    Plugins subscribe to events via :meth:`subscribe`. Core emits events
    at each pipeline stage. No plugin modifies core — they only observe
    and react through the event system.

    Handlers are awaited concurrently with :func:`asyncio.gather`.
    A failing handler is logged but does not block the pipeline.
    """

    def __init__(self) -> None:
        self._handlers: dict[PipelineEvent, list[EventHandler]] = {}

    def subscribe(self, event: PipelineEvent, handler: EventHandler) -> None:
        """Register *handler* to be called when *event* is emitted.

        Multiple handlers may be registered for the same event.
        Duplicate registrations are allowed (the same callable will
        be invoked as many times as it was added).
        """
        self._handlers.setdefault(event, []).append(handler)

    def unsubscribe(self, event: PipelineEvent, handler: EventHandler) -> None:
        """Remove a previously registered *handler* for *event*.

        If the handler was registered multiple times, only the first
        occurrence is removed.  Does nothing if the handler was never
        registered.
        """
        if event in self._handlers:
            try:
                idx = self._handlers[event].index(handler)
                del self._handlers[event][idx]
            except ValueError:
                pass

    async def emit(self, event: PipelineEvent, session: Session) -> None:
        """Fire *event* with *session* to all subscribed handlers.

        All handlers run concurrently.  Exceptions raised by a handler
        are logged with a warning but do not propagate — the pipeline
        continues uninterrupted.
        """
        handlers = self._handlers.get(event, [])
        # Filter out None handlers (accepted at subscribe, no-op at emit)
        handlers = [h for h in handlers if h is not None]
        if not handlers:
            return
        results = await asyncio.gather(
            *[h(event, session) for h in handlers],
            return_exceptions=True,
        )
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Event handler %s failed for %s: %s",
                    handler.__name__,
                    event,
                    result,
                )