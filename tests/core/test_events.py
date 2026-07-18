"""Comprehensive tests for piifilter.events.bus — EventBus, PipelineEvent, AuditTrailPlugin, NoOpEventBus.

Tests subscribe/emit/unsubscribe, error isolation, concurrent handlers,
event enumeration, noop bus, and audit trail lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from piifilter.events.bus import EventBus, PipelineEvent
from piifilter.events.noop import NoOpEventBus
from piifilter.events.audit import AuditTrailPlugin


# ── Helper types ─────────────────────────────────────────────────────────


@dataclass
class FakeSession:
    """Minimal session for event bus tests (avoids real Session dep)."""
    request_id: str
    audit_events: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def session():
    return FakeSession(request_id="test-session-001")


# ── PipelineEvent Enum ───────────────────────────────────────────────────


class TestPipelineEventEnum:
    """PipelineEvent enumeration completeness."""

    def test_all_events_defined(self):
        """13 pipeline lifecycle events must be defined."""
        assert len(PipelineEvent) == 13

    def test_events_have_correct_values(self):
        assert PipelineEvent.BEFORE_DETECTION.value == "before_detection"
        assert PipelineEvent.AFTER_DETECTION.value == "after_detection"
        assert PipelineEvent.BEFORE_RISK.value == "before_risk"
        assert PipelineEvent.AFTER_RISK.value == "after_risk"
        assert PipelineEvent.BEFORE_POLICY.value == "before_policy"
        assert PipelineEvent.AFTER_POLICY.value == "after_policy"
        assert PipelineEvent.BEFORE_REPLACEMENT.value == "before_replacement"
        assert PipelineEvent.AFTER_REPLACEMENT.value == "after_replacement"
        assert PipelineEvent.BEFORE_FORWARD.value == "before_forward"
        assert PipelineEvent.AFTER_FORWARD.value == "after_forward"
        assert PipelineEvent.PIPELINE_START.value == "pipeline_start"
        assert PipelineEvent.PIPELINE_END.value == "pipeline_end"
        assert PipelineEvent.PIPELINE_ERROR.value == "pipeline_error"

    def test_all_events_are_strings(self):
        for evt in PipelineEvent:
            assert isinstance(evt.value, str)


# ── Subscribe / Emit ─────────────────────────────────────────────────────


class TestEventBusSubscribe:
    """Subscribing handlers to the event bus."""

    async def test_subscribe_single_handler(self, bus, session):
        collected = []
        async def handler(evt, sess):
            collected.append((evt.value, sess.request_id))

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        await bus.emit(PipelineEvent.PIPELINE_START, session)

        assert len(collected) == 1
        assert collected[0] == ("pipeline_start", "test-session-001")

    async def test_subscribe_multiple_handlers(self, bus, session):
        collected1 = []
        collected2 = []

        async def h1(evt, sess):
            collected1.append(evt.value)

        async def h2(evt, sess):
            collected2.append(evt.value)

        bus.subscribe(PipelineEvent.PIPELINE_START, h1)
        bus.subscribe(PipelineEvent.PIPELINE_START, h2)
        await bus.emit(PipelineEvent.PIPELINE_START, session)

        assert len(collected1) == 1
        assert len(collected2) == 1

    async def test_multiple_events(self, bus, session):
        collected = []
        async def handler(evt, sess):
            collected.append(evt.value)

        for evt in [PipelineEvent.PIPELINE_START, PipelineEvent.BEFORE_DETECTION, PipelineEvent.PIPELINE_END]:
            bus.subscribe(evt, handler)

        await bus.emit(PipelineEvent.PIPELINE_START, session)
        await bus.emit(PipelineEvent.BEFORE_DETECTION, session)
        await bus.emit(PipelineEvent.PIPELINE_END, session)

        assert collected == ["pipeline_start", "before_detection", "pipeline_end"]

    async def test_emit_no_handlers_no_error(self, bus, session):
        """Emitting an event with no subscribers doesn't raise."""
        await bus.emit(PipelineEvent.PIPELINE_START, session)  # should not raise

    async def test_duplicate_registration(self, bus, session):
        """Registering the same handler twice invokes it twice."""
        count = 0
        async def handler(evt, sess):
            nonlocal count
            count += 1

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        await bus.emit(PipelineEvent.PIPELINE_START, session)

        assert count == 2  # handler invoked twice


class TestEventBusUnsubscribe:
    """Unsubscribing handlers from the event bus."""

    async def test_unsubscribe_removes_handler(self, bus, session):
        collected = []
        async def handler(evt, sess):
            collected.append(evt.value)

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        bus.unsubscribe(PipelineEvent.PIPELINE_START, handler)
        await bus.emit(PipelineEvent.PIPELINE_START, session)

        assert len(collected) == 0

    async def test_unsubscribe_specific_event(self, bus, session):
        """Unsubscribing from one event doesn't affect others."""
        collected = []
        async def handler(evt, sess):
            collected.append(evt.value)

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        bus.subscribe(PipelineEvent.PIPELINE_END, handler)
        bus.unsubscribe(PipelineEvent.PIPELINE_START, handler)

        await bus.emit(PipelineEvent.PIPELINE_START, session)
        await bus.emit(PipelineEvent.PIPELINE_END, session)

        assert collected == ["pipeline_end"]

    async def test_unsubscribe_unregistered_handler_does_nothing(self, bus, session):
        """Unsubscribing a handler that was never registered is a no-op."""
        async def handler(evt, sess):
            pass

        bus.unsubscribe(PipelineEvent.PIPELINE_START, handler)  # should not raise
        bus.unsubscribe(PipelineEvent.BEFORE_DETECTION, handler)  # should not raise

    async def test_unsubscribe_one_of_duplicates(self, bus, session):
        """If the same handler is registered twice, unsubscribe removes only one."""
        count = 0
        async def handler(evt, sess):
            nonlocal count
            count += 1

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        bus.unsubscribe(PipelineEvent.PIPELINE_START, handler)

        await bus.emit(PipelineEvent.PIPELINE_START, session)
        assert count == 1  # one remaining


class TestEventBusErrorHandling:
    """Error isolation in event handlers."""

    async def test_failing_handler_does_not_block_others(self, bus, session):
        """A handler that raises doesn't prevent other handlers from running."""
        results = []

        async def failing(evt, sess):
            raise ValueError("oops")

        async def good(evt, sess):
            results.append("ok")

        bus.subscribe(PipelineEvent.PIPELINE_START, failing)
        bus.subscribe(PipelineEvent.PIPELINE_START, good)

        # Should not raise despite the failing handler
        await bus.emit(PipelineEvent.PIPELINE_START, session)

        assert results == ["ok"]

    async def test_emit_returns_normally_on_handler_error(self, bus, session):
        """emit() doesn't propagate handler exceptions."""
        async def handler(evt, sess):
            raise RuntimeError("handler failed")

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        # No exception should propagate
        await bus.emit(PipelineEvent.PIPELINE_START, session)

    async def test_multiple_failing_handlers(self, bus, session):
        """Multiple failing handlers don't block each other."""
        results = []
        async def fail1(evt, sess):
            raise ValueError("fail1")
        async def fail2(evt, sess):
            raise RuntimeError("fail2")
        async def ok(evt, sess):
            results.append("ok")

        bus.subscribe(PipelineEvent.PIPELINE_START, fail1)
        bus.subscribe(PipelineEvent.PIPELINE_START, fail2)
        bus.subscribe(PipelineEvent.PIPELINE_START, ok)

        await bus.emit(PipelineEvent.PIPELINE_START, session)
        assert results == ["ok"]


class TestEventBusConcurrency:
    """Concurrent handler execution."""

    async def test_handlers_run_concurrently(self, bus, session):
        """Handlers are gathered with asyncio.gather (concurrent)."""
        import asyncio
        order = []

        async def slow1(evt, sess):
            await asyncio.sleep(0.02)
            order.append("slow1")

        async def slow2(evt, sess):
            await asyncio.sleep(0.01)
            order.append("slow2")

        bus.subscribe(PipelineEvent.PIPELINE_START, slow1)
        bus.subscribe(PipelineEvent.PIPELINE_START, slow2)

        await bus.emit(PipelineEvent.PIPELINE_START, session)

        # slow2 should finish first, but both must be done
        assert order == ["slow2", "slow1"]
        assert len(order) == 2

    async def test_large_number_of_handlers(self, bus, session):
        """Many handlers can be registered and executed."""
        n = 50
        counter = 0

        async def handler(evt, sess):
            nonlocal counter
            counter += 1

        for _ in range(n):
            bus.subscribe(PipelineEvent.PIPELINE_START, handler)

        await bus.emit(PipelineEvent.PIPELINE_START, session)
        assert counter == n


class TestNoOpEventBus:
    """NoOpEventBus discarding behaviour."""

    def test_is_event_bus_subclass(self):
        assert issubclass(NoOpEventBus, EventBus)

    async def test_subscribe_is_noop(self):
        bus = NoOpEventBus()
        collected = []
        async def handler(evt, sess):
            collected.append(evt.value)
        bus.subscribe(PipelineEvent.PIPELINE_START, handler)  # should not blow up

    async def test_unsubscribe_is_noop(self):
        bus = NoOpEventBus()
        async def handler(evt, sess):
            pass
        bus.unsubscribe(PipelineEvent.PIPELINE_START, handler)  # should not blow up

    async def test_emit_is_noop(self):
        bus = NoOpEventBus()
        collected = []
        async def handler(evt, sess):
            collected.append(evt.value)
        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        await bus.emit(PipelineEvent.PIPELINE_START, FakeSession(request_id="test"))
        assert len(collected) == 0

    async def test_subscribe_then_emit_nothing_happens(self):
        bus = NoOpEventBus()
        counter = 0
        async def inc(evt, sess):
            nonlocal counter
            counter += 1
        for evt in PipelineEvent:
            bus.subscribe(evt, inc)
        await bus.emit(PipelineEvent.PIPELINE_START, FakeSession(request_id="x"))
        assert counter == 0


class TestAuditTrailPlugin:
    """AuditTrailPlugin lifecycle and behaviour."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.fixture
    def plugin(self, bus):
        return AuditTrailPlugin(bus)

    async def test_plugin_interface(self, plugin):
        assert plugin.name == "audit_trail"
        assert plugin.version == "1.0.0"
        meta = plugin.metadata()
        assert meta["name"] == "audit_trail"
        assert "description" in meta

    async def test_initialize_subscribes_to_all_events(self, bus, plugin):
        session = FakeSession(request_id="test")
        await plugin.initialize()

        # Emit all events
        for evt in PipelineEvent:
            await bus.emit(evt, session)

        assert len(session.audit_events) == len(PipelineEvent)
        for entry in session.audit_events:
            assert "event" in entry
            assert "timestamp" in entry
            assert "request_id" in entry
            assert entry["request_id"] == "test"
            # No prompt content in audit trail
            assert "prompt" not in entry
            assert "payload" not in entry

    async def test_shutdown_stops_recording(self, bus, plugin):
        session = FakeSession(request_id="test")
        await plugin.initialize()
        await bus.emit(PipelineEvent.PIPELINE_START, session)
        assert len(session.audit_events) == 1

        await plugin.shutdown()
        await bus.emit(PipelineEvent.BEFORE_DETECTION, session)
        # Should still be 1 (no new events recorded)
        assert len(session.audit_events) == 1

    async def test_reinitialize_works(self, bus, plugin):
        session = FakeSession(request_id="test")
        await plugin.initialize()
        await bus.emit(PipelineEvent.PIPELINE_START, session)
        assert len(session.audit_events) == 1

        await plugin.shutdown()
        await plugin.initialize()
        await bus.emit(PipelineEvent.PIPELINE_END, session)
        assert len(session.audit_events) == 2

    async def test_idempotent_initialize(self, bus, plugin):
        """Calling initialize twice doesn't duplicate subscriptions."""
        session = FakeSession(request_id="test")
        await plugin.initialize()
        await plugin.initialize()  # second call should be no-op

        await bus.emit(PipelineEvent.PIPELINE_START, session)
        # Only one audit event despite two initializations
        assert len(session.audit_events) == 1

    async def test_idempotent_shutdown(self, bus, plugin):
        """Calling shutdown twice doesn't raise."""
        await plugin.shutdown()
        await plugin.shutdown()  # should not raise

    async def test_audit_trail_format(self, bus, plugin, session):
        """Verify the structure of each audit trail entry."""
        await plugin.initialize()
        await bus.emit(PipelineEvent.PIPELINE_START, session)

        entry = session.audit_events[0]
        assert isinstance(entry["event"], str)
        assert isinstance(entry["timestamp"], (int, float))
        assert isinstance(entry["request_id"], str)

    async def test_all_events_audited(self, bus, plugin):
        """Each PipelineEvent corresponds to an audit entry."""
        s = FakeSession(request_id="all-events")
        await plugin.initialize()

        for evt in PipelineEvent:
            await bus.emit(evt, s)

        audited_events = {e["event"] for e in s.audit_events}
        expected_events = {e.value for e in PipelineEvent}
        assert audited_events == expected_events


class TestEventBusEdgeCases:
    """Edge cases for EventBus."""

    async def test_emit_unknown_event(self, bus, session):
        """Emitting an event value not in the PipelineEvent enum is still accepted."""
        class FakeEvent:
            value = "nonexistent_event"
        await bus.emit(FakeEvent(), session)  # Should not raise

    async def test_subscribe_null_handler(self, bus):
        """Subscribing None as a handler will fail at emit time, not subscribe time."""
        bus.subscribe(PipelineEvent.PIPELINE_START, None)  # type: ignore[arg-type]
        s = FakeSession(request_id="x")
        # Will raise TypeError during gather, which is caught by emit
        await bus.emit(PipelineEvent.PIPELINE_START, s)  # Should not propagate

    async def test_subscribe_then_emit_different_event(self, bus, session):
        """Handler only fires for the subscribed event."""
        collected = []
        async def handler(evt, sess):
            collected.append(evt.value)

        bus.subscribe(PipelineEvent.PIPELINE_START, handler)
        await bus.emit(PipelineEvent.BEFORE_DETECTION, session)

        assert len(collected) == 0