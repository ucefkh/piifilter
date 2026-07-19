"""Comprehensive tests for piifilter.session.Session.

Covers creation, property aliases, audit events, timing, blocking,
replacement_map, dataclass round-trip, and edge cases.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime, timedelta

import pytest

from piifilter.session import Session
from piifilter.shared.models import (
    DetectedEntity,
    EntityType,
    Replacement,
    ReplacementMode,
    RiskAssessment,
    RiskLevel,
)
from piifilter.config import FilterConfig, ProviderConfig


class TestSessionCreation:
    """Session construction and default values."""

    def test_default_creation(self):
        """A Session created with just a prompt gets sensible defaults."""
        s = Session(prompt="Hello, world")
        assert s.prompt == "Hello, world"
        assert s.request_id and len(s.request_id) == 16
        assert s.conversation_id is None
        assert s.mode is None
        assert s.entities == []
        assert s.risk is None
        assert s.replacements == []
        assert s.filtered_prompt is None
        assert s.llm_response is None
        assert s.blocked is False
        assert s.block_reason is None
        assert isinstance(s.config, FilterConfig)
        assert s.policy is None
        assert s.provider_config is None
        assert s.replacement_map == {}
        assert s.statistics == {}
        assert s.audit_events == []
        assert s.metadata == {}
        assert s.started_at is None
        assert s.completed_at is None

    def test_property_aliases(self):
        """is_blocked mirrors blocked."""
        s = Session(prompt="test")
        assert s.is_blocked is False
        s.blocked = True
        assert s.is_blocked is True

    def test_latency_ms_zero_when_incomplete(self):
        """latency_ms returns 0.0 when pipeline hasn't completed."""
        s = Session(prompt="test")
        assert s.latency_ms == 0.0
        s.mark_started()
        assert s.latency_ms == 0.0  # started but not completed

    def test_latency_ms_positive_when_complete(self):
        """latency_ms returns elapsed ms after both mark_started and mark_completed."""
        s = Session(prompt="test")
        s.mark_started()
        time.sleep(0.005)
        s.mark_completed()
        assert s.latency_ms > 4.0  # at least 5ms (with tolerance)

    def test_custom_request_id(self):
        """User-supplied request_id is honoured."""
        s = Session(prompt="test", request_id="custom-001")
        assert s.request_id == "custom-001"

    def test_unique_request_ids(self):
        """Each new session gets a unique request_id by default."""
        s1 = Session(prompt="a")
        s2 = Session(prompt="b")
        assert s1.request_id != s2.request_id

    def test_conversation_id(self):
        """conversation_id is set if provided."""
        s = Session(prompt="test", conversation_id="conv-abc")
        assert s.conversation_id == "conv-abc"

    def test_mode_passthrough(self):
        """ReplacementMode is stored as-is."""
        s = Session(prompt="test", mode=ReplacementMode.MASK)
        assert s.mode == ReplacementMode.MASK

    def test_provider_config(self):
        """ProviderConfig is accepted."""
        s = Session(prompt="test", provider_config=ProviderConfig(name="openai"))
        assert s.provider_config is not None
        assert s.provider_config.name == "openai"

    def test_policy_dict(self):
        """Policy dict is stored."""
        s = Session(prompt="test", policy={"rules": []})
        assert s.policy == {"rules": []}


class TestSessionTiming:
    """mark_started / mark_completed / latency_ms."""

    def test_mark_started_sets_timestamp(self):
        s = Session(prompt="test")
        before = datetime.utcnow()
        s.mark_started()
        after = datetime.utcnow()
        assert s.started_at is not None
        assert before <= s.started_at <= after

    def test_mark_completed_sets_timestamp(self):
        s = Session(prompt="test")
        before = datetime.utcnow()
        s.mark_completed()
        after = datetime.utcnow()
        assert s.completed_at is not None
        assert before <= s.completed_at <= after

    def test_both_marked_latency_is_positive(self):
        s = Session(prompt="test")
        s.mark_started()
        s.mark_completed()
        assert s.latency_ms >= 0.0

    def test_latency_millisecond_precision(self):
        """latency_ms is in milliseconds, not seconds."""
        s = Session(prompt="test")
        s.mark_started()
        s.mark_completed()
        assert s.latency_ms < 1000.0  # sanity: never more than 1 second


class TestSessionAudit:
    """add_audit and audit_events."""

    def test_add_audit_creates_entry(self):
        s = Session(prompt="test")
        s.add_audit("detect", "entity_found", {"count": 3})
        assert len(s.audit_events) == 1
        entry = s.audit_events[0]
        assert entry["stage"] == "detect"
        assert entry["event"] == "entity_found"
        assert entry["data"] == {"count": 3}

    def test_add_audit_adds_timestamp(self):
        s = Session(prompt="test")
        s.add_audit("x", "y", {})
        assert "timestamp" in s.audit_events[0]
        assert s.audit_events[0]["timestamp"] is not None

    def test_multiple_audit_events(self):
        s = Session(prompt="test")
        s.add_audit("a", "e1", {})
        s.add_audit("b", "e2", {})
        s.add_audit("c", "e3", {})
        assert len(s.audit_events) == 3
        assert [e["stage"] for e in s.audit_events] == ["a", "b", "c"]

    def test_audit_events_append_does_not_replace(self):
        """Calling add_audit repeatedly does not wipe earlier entries."""
        s = Session(prompt="test")
        s.add_audit("s1", "evt1", {"n": 1})
        s.add_audit("s2", "evt2", {"n": 2})
        assert s.audit_events[0]["data"]["n"] == 1
        assert s.audit_events[1]["data"]["n"] == 2

    def test_audit_with_empty_data(self):
        s = Session(prompt="test")
        s.add_audit("check", "ok", {})
        assert s.audit_events[0]["data"] == {}

    def test_audit_stage_naming_convention(self):
        """Stage names can be any string (no validation)."""
        s = Session(prompt="test")
        s.add_audit("🔄 stage with emoji", "some_event", {"key": "val"})
        assert s.audit_events[0]["stage"] == "🔄 stage with emoji"


class TestSessionBlocking:
    """blocked / block_reason / is_blocked."""

    def test_default_not_blocked(self):
        s = Session(prompt="test")
        assert s.blocked is False
        assert s.is_blocked is False
        assert s.block_reason is None

    def test_block_flag(self):
        s = Session(prompt="test")
        s.blocked = True
        assert s.is_blocked is True

    def test_block_with_reason(self):
        s = Session(prompt="test")
        s.blocked = True
        s.block_reason = "high_risk_detected"
        assert s.is_blocked
        assert s.block_reason == "high_risk_detected"

    def test_unblock(self):
        s = Session(prompt="test")
        s.blocked = True
        s.blocked = False
        assert s.is_blocked is False


class TestSessionReplacementMap:
    """replacement_map dict operations."""

    def test_default_empty(self):
        s = Session(prompt="test")
        assert s.replacement_map == {}

    def test_add_entry(self):
        s = Session(prompt="test")
        s.replacement_map["john@example.com"] = "[EMAIL]"
        assert s.replacement_map["john@example.com"] == "[EMAIL]"

    def test_multiple_entries(self):
        s = Session(prompt="test")
        s.replacement_map["alice@example.com"] = "[EMAIL_1]"
        s.replacement_map["bob@example.com"] = "[EMAIL_2]"
        assert len(s.replacement_map) == 2

    def test_update_existing(self):
        s = Session(prompt="test")
        s.replacement_map["key"] = "old"
        s.replacement_map["key"] = "new"
        assert s.replacement_map["key"] == "new"

    def test_delete(self):
        s = Session(prompt="test")
        s.replacement_map["x"] = "y"
        del s.replacement_map["x"]
        assert "x" not in s.replacement_map


class TestSessionEntities:
    """DetectedEntity interaction via Session."""

    def test_append_entity(self):
        s = Session(prompt="My email is john@example.com")
        e = DetectedEntity(
            entity_type=EntityType.EMAIL,
            value="john@example.com",
            start=11,
            end=27,
            confidence=0.98,
            detector="regex",
        )
        s.entities.append(e)
        assert len(s.entities) == 1
        assert s.entities[0].type == EntityType.EMAIL
        assert s.entities[0].text == "john@example.com"
        assert s.entities[0].score == 0.98
        assert s.entities[0].length == 16

    def test_entity_property_aliases(self):
        """DetectedEntity's type/text/score aliases work through Session."""
        e = DetectedEntity(EntityType.PHONE, "555-0100", 0, 9)
        assert e.type == EntityType.PHONE
        assert e.type is e.entity_type
        assert e.text == "555-0100"
        assert e.text is e.value
        assert e.score == 1.0
        assert e.score is e.confidence

    def test_multiple_entities(self):
        s = Session(prompt="Contact john@example.com or 555-0100")
        s.entities.append(
            DetectedEntity(EntityType.EMAIL, "john@example.com", 8, 24)
        )
        s.entities.append(
            DetectedEntity(EntityType.PHONE, "555-0100", 28, 36)
        )
        assert len(s.entities) == 2
        assert s.entities[0].type == EntityType.EMAIL
        assert s.entities[1].type == EntityType.PHONE

    def test_entity_with_votes_and_source(self):
        e = DetectedEntity(
            EntityType.API_KEY, "sk-abc", 0, 6,
            confidence=0.95,
            detector="regex_detector",
            source_detector="regex_v2",
            detector_votes=[{"detector": "regex", "confidence": 0.95}],
        )
        assert e.detector == "regex_detector"
        assert e.source_detector == "regex_v2"
        assert len(e.detector_votes) == 1

    def test_entity_len(self):
        e = DetectedEntity(EntityType.API_KEY, "sk-abc123", 0, 9)
        assert len(e) == 9
        assert e.length == 9


class TestSessionRisk:
    """RiskAssessment integration."""

    def test_risk_default_none(self):
        s = Session(prompt="test")
        assert s.risk is None

    def test_set_risk_assessment(self):
        s = Session(prompt="test")
        s.risk = RiskAssessment(score=85.0, level=RiskLevel.HIGH)
        assert s.risk.score == 85.0
        assert s.risk.level == RiskLevel.HIGH

    def test_risk_is_critical(self):
        r = RiskAssessment(score=95.0, level=RiskLevel.CRITICAL)
        assert r.is_critical()

    def test_risk_is_not_critical(self):
        r = RiskAssessment(score=20.0, level=RiskLevel.LOW)
        assert not r.is_critical()

    def test_risk_with_string_level(self):
        """RiskLevel accepts string forms too."""
        r = RiskAssessment(score=60.0, level="MEDIUM")
        assert not r.is_critical()

    def test_risk_with_details(self):
        r = RiskAssessment(
            score=50.0,
            level=RiskLevel.MEDIUM,
            detected_count=2,
            critical_entities=["EMAIL"],
            recommendation="Review",
            details=[{"type": "EMAIL", "points": 10}],
        )
        assert r.detected_count == 2
        assert r.critical_entities == ["EMAIL"]
        assert r.recommendation == "Review"
        assert len(r.details) == 1

    def test_risk_with_reason_codes(self):
        r = RiskAssessment(score=30.0, level=RiskLevel.LOW, reason_codes=["test_code"])
        assert "test_code" in r.reason_codes

    def test_risk_default_values(self):
        """RiskAssessment has sensible defaults."""
        r = RiskAssessment()
        assert r.score == 0.0
        assert r.level == RiskLevel.LOW
        assert r.detected_count == 0


class TestSessionReplacements:
    """Replacement entries on Session."""

    def test_default_empty(self):
        s = Session(prompt="test")
        assert s.replacements == []

    def test_append_replacement(self):
        s = Session(prompt="test")
        r = Replacement(
            original="john@example.com",
            replacement="[EMAIL]",
            entity_type=EntityType.EMAIL,
            start=0,
            end=16,
            mode=ReplacementMode.MASK,
        )
        s.replacements.append(r)
        assert len(s.replacements) == 1
        assert s.replacements[0].original == "john@example.com"
        assert s.replacements[0].replacement == "[EMAIL]"
        assert s.replacements[0].mode == ReplacementMode.MASK

    def test_replacement_not_reversible(self):
        r = Replacement(
            original="test", replacement="***",
            entity_type=EntityType.API_KEY, start=0, end=4,
        )
        assert r.mode == ReplacementMode.SEMANTIC

    def test_replacement_default_mode(self):
        r = Replacement(
            original="a", replacement="b",
            entity_type=EntityType.PERSON, start=0, end=1,
        )
        assert r.mode == ReplacementMode.SEMANTIC


class TestSessionDataclass:
    """dataclasses.asdict round-trip and serialization."""

    def test_asdict_basic(self):
        s = Session(prompt="Hello")
        d = dataclasses.asdict(s)
        assert d["prompt"] == "Hello"
        assert d["blocked"] is False
        assert d["entities"] == []

    def test_asdict_with_entities(self):
        s = Session(prompt="test")
        s.entities.append(
            DetectedEntity(EntityType.EMAIL, "a@b.com", 0, 8)
        )
        d = dataclasses.asdict(s)
        assert len(d["entities"]) == 1

    def test_asdict_with_audit_events(self):
        s = Session(prompt="test")
        s.add_audit("st", "ev", {"k": "v"})
        d = dataclasses.asdict(s)
        assert len(d["audit_events"]) == 1
        assert d["audit_events"][0]["stage"] == "st"
        assert d["audit_events"][0]["data"]["k"] == "v"


class TestSessionConfig:
    """Config integration on Session."""

    def test_default_config_provided(self):
        s = Session(prompt="test")
        assert s.config.replacement.default_strategy == "semantic"
        assert s.config.logging.level == "INFO"

    def test_custom_config(self):
        from piifilter.config import FilterConfig, DetectionConfig
        cfg = FilterConfig(detection=DetectionConfig(confidence_threshold=0.9))
        s = Session(prompt="test", config=cfg)
        assert s.config.detection.confidence_threshold == 0.9

    def test_statistics_dict(self):
        s = Session(prompt="test")
        s.statistics["entities_found"] = 3
        s.statistics["latency_ms"] = 12.5
        assert s.statistics["entities_found"] == 3
        assert s.statistics["latency_ms"] == 12.5

    def test_metadata_dict(self):
        s = Session(prompt="test")
        s.metadata["client_ip"] = "192.168.1.1"
        s.metadata["user_agent"] = "test"
        assert s.metadata["client_ip"] == "192.168.1.1"

    def test_filtered_prompt(self):
        s = Session(prompt="original text")
        s.filtered_prompt = "[REDACTED]"
        assert s.filtered_prompt == "[REDACTED]"

    def test_llm_response(self):
        s = Session(prompt="test")
        s.llm_response = "Hello, how can I help?"
        assert s.llm_response == "Hello, how can I help?"


class TestSessionEdgeCases:
    """Boundary and edge cases."""

    def test_empty_prompt(self):
        s = Session(prompt="")
        assert s.prompt == ""

    def test_very_long_prompt(self):
        long_text = "A" * 100_000
        s = Session(prompt=long_text)
        assert len(s.prompt) == 100_000

    def test_unicode_prompt(self):
        s = Session(prompt="こんにちは世界 👋")
        assert s.prompt == "こんにちは世界 👋"

    def test_newlines_in_prompt(self):
        s = Session(prompt="line1\nline2\nline3")
        assert len(s.prompt.splitlines()) == 3

    def test_mark_started_multiple_times(self):
        """Calling mark_started again overwrites the timestamp."""
        s = Session(prompt="test")
        s.mark_started()
        t1 = s.started_at
        s.mark_started()
        t2 = s.started_at
        assert t2 >= t1

    def test_mark_completed_before_started(self):
        """Calling mark_completed first still records the timestamp."""
        s = Session(prompt="test")
        s.mark_completed()
        assert s.completed_at is not None
        assert s.started_at is None
        assert s.latency_ms == 0.0  # no started_at