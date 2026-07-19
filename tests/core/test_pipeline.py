"""Comprehensive tests for piifilter.pipeline.FilterPipeline.

Tests the pipeline with mock detectors, strategies, and providers to verify
event flow, blocking, error handling, and replacement without real dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from piifilter.pipeline import FilterPipeline
from piifilter.session import Session
from piifilter.events.bus import EventBus, PipelineEvent
from piifilter.registry.registry import PluginRegistry
from piifilter.config import FilterConfig, PolicyConfig, PolicyRule, ReplacementConfig
from piifilter.shared.models import (
    DetectedEntity,
    EntityType,
    Replacement,
    ReplacementMode,
    RiskLevel,
)


# ── Mock interfaces ──────────────────────────────────────────────────────


class MockDetector:
    """Detector-like object that returns pre-configured entities."""

    def __init__(
        self,
        name: str = "mock_detector",
        entities: list[DetectedEntity] | None = None,
        fail: bool = False,
    ) -> None:
        self.name = name
        self._entities = entities or []
        self._fail = fail

    async def detect(self, session: Session) -> list[DetectedEntity]:
        if self._fail:
            raise RuntimeError("Detector failure")
        return self._entities

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class MockStrategy:
    """Strategy-like object that replaces entities with formatted markers."""

    def __init__(self, name: str = "mock_strategy") -> None:
        self.name = name

    async def replace(
        self, session: Session, entities: list[DetectedEntity]
    ) -> tuple[str, list[Replacement]]:
        text = session.prompt
        replacements = []
        for e in sorted(entities, key=lambda x: x.start, reverse=True):
            repl = f"[{e.type.value.upper()}]"
            text = text[: e.start] + repl + text[e.end :]
            replacements.append(
                Replacement(
                    original=e.value,
                    replacement=repl,
                    entity_type=e.entity_type,
                    start=e.start,
                    end=e.end,
                    mode=ReplacementMode.MASK,
                )
            )
        return text, replacements

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class MockMaskStrategy:
    """Mock strategy that replaces entities with [TYPE] markers, registered as 'semantic'."""

    name = "semantic"
    version = "1.0.0"

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def replace(
        self, session: Session, entities: list[DetectedEntity]
    ) -> tuple[str, list[Replacement]]:
        text = session.prompt
        replacements = []
        for entity in sorted(entities, key=lambda e: e.start, reverse=True):
            replacement = f"[{entity.entity_type.value}]"
            text = text[: entity.start] + replacement + text[entity.end :]
            replacements.append(
                Replacement(
                    original=entity.value,
                    replacement=replacement,
                    entity_type=entity.entity_type,
                )
            )
        return text, replacements


class MockProvider:
    """Provider-like object that echoes the filtered prompt."""

    def __init__(self, name: str = "mock_provider") -> None:
        self.name = name

    async def forward(self, session: Session) -> str:
        return f"Mock response: {session.filtered_prompt}"

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def registry():
    return PluginRegistry(allow_overwrite=True)


@pytest.fixture
def pipeline(event_bus, registry):
    p = FilterPipeline(
        config=FilterConfig(),
        registry=registry,
        event_bus=event_bus,
    )
    p.registry.register_strategy(MockMaskStrategy())
    return p


@pytest.fixture
def basic_session():
    return Session(prompt="My email is john@example.com and phone is 555-0100")


@pytest.fixture
def email_entity():
    return DetectedEntity(
        EntityType.EMAIL, "john@example.com", 11, 27, confidence=0.95, detector="mock"
    )


@pytest.fixture
def phone_entity():
    return DetectedEntity(
        EntityType.PHONE, "555-0100", 38, 46, confidence=0.90, detector="mock"
    )


class TestPipelineConstruction:
    """FilterPipeline construction and defaults."""

    def test_default_construction(self):
        p = FilterPipeline()
        assert isinstance(p.config, FilterConfig)
        assert isinstance(p.registry, PluginRegistry)
        assert isinstance(p.event_bus, EventBus)

    def test_custom_config(self):
        cfg = FilterConfig(
            replacement=ReplacementConfig(default_strategy="mask")
        )
        p = FilterPipeline(config=cfg)
        assert p.config.replacement.default_strategy == "mask"

    def test_custom_registry(self):
        reg = PluginRegistry(allow_overwrite=True)
        p = FilterPipeline(registry=reg)
        assert p.registry is reg

    def test_custom_event_bus(self):
        eb = EventBus()
        p = FilterPipeline(event_bus=eb)
        assert p.event_bus is eb


class TestPipelineEvents:
    """Verify events are emitted at expected stages."""

    async def test_all_lifecycle_events_emitted(self, pipeline, basic_session, event_bus):
        """The full chain emits all expected pipeline events."""
        collected = []

        async def capture(event, session):
            collected.append(event.value)

        for evt in PipelineEvent:
            event_bus.subscribe(evt, capture)

        # Register a mock detector (needed so pipeline runs the detect stage
        # rather than skipping immediately)
        pipeline.registry.register_detector(MockDetector("noop"))

        await pipeline.run(basic_session)

        expected = [
            PipelineEvent.PIPELINE_START.value,
            PipelineEvent.BEFORE_DETECTION.value,
            PipelineEvent.AFTER_DETECTION.value,
            PipelineEvent.BEFORE_RISK.value,
            PipelineEvent.AFTER_RISK.value,
            PipelineEvent.BEFORE_POLICY.value,
            PipelineEvent.AFTER_POLICY.value,
            PipelineEvent.BEFORE_REPLACEMENT.value,
            PipelineEvent.AFTER_REPLACEMENT.value,
            PipelineEvent.PIPELINE_END.value,
        ]
        assert collected == expected, f"Got {collected}"

    async def test_forward_events_when_provider(self, pipeline, basic_session, event_bus):
        """BEFORE_FORWARD and AFTER_FORWARD are emitted when provider_config is set."""
        collected = []
        async def capture(event, session):
            collected.append(event.value)

        pipeline.registry.register_detector(MockDetector("noop"))
        pipeline.registry.register_provider(MockProvider("mock_provider"))

        for evt in PipelineEvent:
            event_bus.subscribe(evt, capture)

        basic_session.provider_config = type(
            "Obj", (), {"name": "mock_provider"}
        )()

        await pipeline.run(basic_session)

        assert PipelineEvent.BEFORE_FORWARD.value in collected
        assert PipelineEvent.AFTER_FORWARD.value in collected

    async def test_error_event_on_failure(self, pipeline, basic_session, event_bus):
        """PIPELINE_ERROR is emitted when a stage fails."""
        collected = []
        async def capture(event, session):
            collected.append(event.value)

        event_bus.subscribe(PipelineEvent.PIPELINE_ERROR, capture)

        # Register a detector that raises
        pipeline.registry.register_detector(MockDetector("fail", fail=True))

        await pipeline.run(basic_session)

        assert PipelineEvent.PIPELINE_ERROR.value in collected

    async def test_pipeline_end_always_emitted(self, pipeline, basic_session, event_bus):
        """PIPELINE_END is emitted even after errors."""
        collected = []
        async def capture(event, session):
            collected.append(event.value)

        event_bus.subscribe(PipelineEvent.PIPELINE_END, capture)
        pipeline.registry.register_detector(MockDetector("fail", fail=True))

        await pipeline.run(basic_session)

        assert PipelineEvent.PIPELINE_END.value in collected


class TestPipelineDetection:
    """Detection stage behaviour."""

    async def test_detector_results_merged(self, pipeline, basic_session, email_entity, phone_entity):
        mock1 = MockDetector("d1", entities=[email_entity])
        mock2 = MockDetector("d2", entities=[phone_entity])
        pipeline.registry.register_detector(mock1)
        pipeline.registry.register_detector(mock2)

        result = await pipeline.run(basic_session)

        assert len(result.entities) == 2
        types = {e.type for e in result.entities}
        assert EntityType.EMAIL in types
        assert EntityType.PHONE in types

    async def test_detector_failure_isolated(self, pipeline, basic_session, email_entity):
        """A failing detector doesn't stop other detectors from running."""
        fail_det = MockDetector("fail", fail=True)
        good_det = MockDetector("good", entities=[email_entity])
        pipeline.registry.register_detector(fail_det)
        pipeline.registry.register_detector(good_det)

        result = await pipeline.run(basic_session)

        # The good detector's entities should still be there
        assert len(result.entities) == 1
        assert result.entities[0].type == EntityType.EMAIL

    async def test_no_entities_empty_list(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        result = await pipeline.run(basic_session)
        assert result.entities == []

    async def test_deduplication_by_position(self, pipeline, basic_session):
        """Entities with same start/end/type are deduplicated."""
        e1 = DetectedEntity(EntityType.EMAIL, "john@example.com", 11, 27, confidence=0.8)
        e2 = DetectedEntity(EntityType.EMAIL, "john@example.com", 11, 27, confidence=0.95)
        pipeline.registry.register_detector(MockDetector("d1", entities=[e1]))
        pipeline.registry.register_detector(MockDetector("d2", entities=[e2]))

        result = await pipeline.run(basic_session)

        assert len(result.entities) == 1
        # Higher confidence wins
        assert result.entities[0].confidence == 0.95


class TestPipelineRisk:
    """Risk assessment stage."""

    async def test_risk_low_for_no_entities(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        result = await pipeline.run(basic_session)
        assert result.risk is not None
        assert result.risk.score == 0.0
        assert result.risk.level in (RiskLevel.LOW, "LOW")

    async def test_risk_score_increases(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector(
            "d", entities=[DetectedEntity(EntityType.EMAIL, "a@b.com", 0, 8)]
        ))
        result = await pipeline.run(basic_session)
        assert result.risk is not None
        assert result.risk.score > 0
        assert result.risk.detected_count >= 1

    async def test_critical_entities_flagged(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector(
            "d", entities=[DetectedEntity(EntityType.API_KEY, "sk-abc", 0, 7)]
        ))
        result = await pipeline.run(basic_session)
        assert result.risk is not None
        assert "API_KEY" in result.risk.critical_entities or "api_key" in result.risk.critical_entities

    async def test_risk_blocks_at_critical(self, basic_session):
        """Pipeline can be configured to block at critical threshold."""
        cfg = FilterConfig(policy=PolicyConfig(rules=[
            PolicyRule(if_condition={"risk": 80, "operator": ">"}, action="BLOCK"),
        ]))
        p = FilterPipeline(config=cfg, registry=PluginRegistry(allow_overwrite=True))
        p.registry.register_strategy(MockMaskStrategy())
        # EMAIL = 10 pts each; 9 × 10 = 90 > 80 → triggers risk block
        p.registry.register_detector(MockDetector(
            "d", entities=[
                DetectedEntity(EntityType.EMAIL, f"user{i}@example.com", i * 20, i * 20 + 15)
                for i in range(9)
            ]
        ))

        result = await p.run(basic_session)
        assert result.is_blocked
        assert "risk" in (result.block_reason or "").lower()


class TestPipelineBlocking:
    """Pipeline blocking via policy rules."""

    async def test_block_on_api_key(self, pipeline, basic_session):
        """Default policy blocks API_KEY entities."""
        pipeline.registry.register_detector(MockDetector(
            "d", entities=[DetectedEntity(EntityType.API_KEY, "sk-abc123", 0, 9)]
        ))
        # Use the default config which has BLOCK for API_KEY
        result = await pipeline.run(basic_session)
        assert result.is_blocked
        assert result.block_reason is not None

    async def test_no_block_on_low_risk(self, pipeline, basic_session, email_entity):
        """Email (non-blocked type) does not trigger block."""
        pipeline.registry.register_detector(MockDetector("d", entities=[email_entity]))
        result = await pipeline.run(basic_session)
        assert not result.is_blocked

    async def test_block_reason_recorded(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector(
            "d", entities=[DetectedEntity(EntityType.CREDIT_CARD, "4111-1111-1111-1111", 0, 19)]
        ))
        # CREDIT_CARD isn't in the default block list, so add a policy rule for it
        basic_session.config.policy.rules.append(
            PolicyRule(if_condition={"type": "CREDIT_CARD"}, action="BLOCK")
        )
        result = await pipeline.run(basic_session)
        assert result.is_blocked
        assert "BLOCK" in (result.block_reason or "")
        assert "credit_card" in (result.block_reason or "").lower()


class TestPipelineReplacement:
    """Replacement stage with mock strategy."""

    async def test_replacement_applied(self, pipeline, basic_session, email_entity):
        mock_strat = MockStrategy("mock_strategy")
        pipeline.registry.register_detector(MockDetector("d", entities=[email_entity]))
        pipeline.registry.register_strategy(mock_strat)

        result = await pipeline.run(basic_session)

        assert result.filtered_prompt is not None
        assert "[EMAIL]" in result.filtered_prompt
        assert "john@example.com" not in result.filtered_prompt

    async def test_no_replacements_when_no_entities(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        pipeline.registry.register_strategy(MockStrategy("mock_strategy"))

        result = await pipeline.run(basic_session)

        # filtered_prompt should be the original when no entities exist
        assert result.filtered_prompt == basic_session.prompt

    async def test_multiple_replacements(self, pipeline, basic_session, email_entity, phone_entity):
        pipeline.registry.register_detector(MockDetector("d", entities=[email_entity, phone_entity]))
        pipeline.registry.register_strategy(MockStrategy("mock_strategy"))

        result = await pipeline.run(basic_session)

        assert "[EMAIL]" in result.filtered_prompt
        assert "[PHONE]" in result.filtered_prompt
        assert len(result.replacements) == 2

    async def test_replacement_with_fallback(self, basic_session, email_entity):
        """Without a registered strategy, falls back to basic replacement."""
        reg = PluginRegistry(allow_overwrite=True)
        p = FilterPipeline(config=FilterConfig(), registry=reg)
        p.registry.register_detector(MockDetector("d", entities=[email_entity]))
        # Don't register a strategy — pipeline falls back to basic replacement

        result = await p.run(basic_session)

        assert result.filtered_prompt is not None
        assert result.filtered_prompt != basic_session.prompt

    async def test_replacement_map_populated(self, pipeline, basic_session, email_entity):
        """Entities should be recorded in replacements list."""
        pipeline.registry.register_detector(MockDetector("d", entities=[email_entity]))
        pipeline.registry.register_strategy(MockStrategy("mock_strategy"))

        result = await pipeline.run(basic_session)

        assert len(result.replacements) >= 1
        assert result.replacements[0].original == "john@example.com"


class TestPipelineForward:
    """Forward stage with mock provider."""

    async def test_forward_with_provider(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        pipeline.registry.register_provider(MockProvider("mock_provider"))
        basic_session.provider_config = type("Obj", (), {"name": "mock_provider"})()

        result = await pipeline.run(basic_session)

        assert result.llm_response is not None
        assert "Mock response:" in result.llm_response

    async def test_forward_missing_provider(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        basic_session.provider_config = type("Obj", (), {"name": "nonexistent_provider"})()

        result = await pipeline.run(basic_session)

        assert result.blocked
        assert "not found" in (result.block_reason or "").lower()

    async def test_no_forward_without_provider_confg(self, pipeline, basic_session):
        """Pipeline skips forward if no provider_config is set on session."""
        pipeline.registry.register_detector(MockDetector("noop"))

        result = await pipeline.run(basic_session)

        assert result.llm_response is None


class TestPipelineAudit:
    """Audit events recorded by pipeline stages."""

    async def test_audit_events_recorded(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        result = await pipeline.run(basic_session)

        assert len(result.audit_events) > 0
        stages = [e["stage"] for e in result.audit_events]
        assert "pipeline" in stages
        assert "detection" in stages
        assert "replacement" in stages

    async def test_audit_contains_request_id(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        result = await pipeline.run(basic_session)

        for entry in result.audit_events:
            assert "timestamp" in entry

    async def test_error_audit_on_failure(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("fail", fail=True))
        result = await pipeline.run(basic_session)

        stages = [e["stage"] for e in result.audit_events]
        assert "pipeline" in stages
        # An error audit entry exists
        error_audits = [e for e in result.audit_events if e.get("event") == "error"]
        assert len(error_audits) > 0


class TestPipelineEdgeCases:
    """Edge cases and error paths."""

    async def test_empty_prompt(self, pipeline):
        s = Session(prompt="")
        pipeline.registry.register_detector(MockDetector("noop"))
        result = await pipeline.run(s)
        assert result.filtered_prompt == ""

    async def test_pipeline_close(self, pipeline):
        """close() shuts down the registry without error."""
        mock = MockDetector("m")
        pipeline.registry.register_detector(mock)
        await pipeline.close()
        # No assertion needed — just shouldn't raise

    async def test_blocked_session_stops_early(self, pipeline, basic_session, email_entity):
        """If blocked is True after detection, pipeline stops."""
        pipeline.registry.register_detector(MockDetector(
            "d", entities=[DetectedEntity(EntityType.API_KEY, "sk-key", 0, 6)]
        ))

        result = await pipeline.run(basic_session)

        assert result.is_blocked
        # Blocked means replacement stage shouldn't run
        assert result.filtered_prompt is None or result.filtered_prompt == basic_session.prompt

    async def test_session_timing(self, pipeline, basic_session):
        pipeline.registry.register_detector(MockDetector("noop"))
        result = await pipeline.run(basic_session)
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.latency_ms > 0