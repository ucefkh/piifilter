"""Tests for the RiskEngine."""
from __future__ import annotations

import pytest
from piifilter.config import FilterConfig
from piifilter.shared.models import DetectedEntity, EntityType, RiskLevel
from piifilter.risk.engine import RiskEngine, _determine_level, _resolve_threshold


@pytest.fixture
def engine() -> RiskEngine:
    return RiskEngine(FilterConfig())


@pytest.fixture
def make_entity():
    """Factory to create a DetectedEntity quickly."""
    return lambda text, etype: DetectedEntity(
        text=text, type=etype, start=0, end=len(text), score=1.0
    )


# ── _determine_level ──────────────────────────────────────────────────────────

class TestDetermineLevel:
    def test_zero(self):
        assert _determine_level(0) == RiskLevel.LOW

    def test_boundary_low(self):
        assert _determine_level(25) == RiskLevel.LOW

    def test_medium(self):
        assert _determine_level(26) == RiskLevel.MEDIUM
        assert _determine_level(50) == RiskLevel.MEDIUM

    def test_high(self):
        assert _determine_level(51) == RiskLevel.HIGH
        assert _determine_level(75) == RiskLevel.HIGH

    def test_critical(self):
        assert _determine_level(76) == RiskLevel.CRITICAL
        assert _determine_level(100) == RiskLevel.CRITICAL


# ── _resolve_threshold ────────────────────────────────────────────────────────

class TestResolveThreshold:
    def test_low(self):
        cfg = FilterConfig()
        cfg.risk.threshold = "low"
        assert _resolve_threshold(cfg) == RiskLevel.LOW

    def test_medium_default(self):
        cfg = FilterConfig()
        assert _resolve_threshold(cfg) == RiskLevel.MEDIUM

    def test_case_insensitive(self):
        cfg = FilterConfig()
        cfg.risk.threshold = "CRITICAL"
        assert _resolve_threshold(cfg) == RiskLevel.CRITICAL

    def test_invalid_falls_back_to_medium(self):
        cfg = FilterConfig()
        cfg.risk.threshold = "bogus"
        assert _resolve_threshold(cfg) == RiskLevel.MEDIUM


# ── RiskEngine.assess ─────────────────────────────────────────────────────────

class TestAssess:
    async def test_no_entities(self, engine: RiskEngine):
        r = await engine.assess("hello", [])
        assert r.score == 0.0
        assert r.level == RiskLevel.LOW
        assert r.detected_count == 0
        assert r.critical_entities == []
        assert r.recommendation == "Proceed — minimal sensitive data detected"

    async def test_single_low_entity(self, engine: RiskEngine, make_entity):
        r = await engine.assess("John", [make_entity("John", EntityType.PERSON)])
        assert r.score == 5.0
        assert r.level == RiskLevel.LOW
        assert r.detected_count == 1

    async def test_critical_entities_list(self, engine: RiskEngine, make_entity):
        r = await engine.assess("x", [
            make_entity("sk-1", EntityType.API_KEY),
            make_entity("jt", EntityType.JWT),
            make_entity("alice", EntityType.PERSON),
        ])
        assert sorted(r.critical_entities, key=lambda e: e.value) == [
            EntityType.API_KEY,
            EntityType.JWT,
        ]

    async def test_four_critical_caps_at_100(self, engine: RiskEngine, make_entity):
        r = await engine.assess("x", [
            make_entity("a", EntityType.API_KEY),
            make_entity("b", EntityType.JWT),
            make_entity("c", EntityType.CREDIT_CARD),
            make_entity("d", EntityType.SOCIAL_SECURITY),
        ])
        assert r.score == 100.0
        assert r.level == RiskLevel.CRITICAL
        assert len(r.critical_entities) == 4

    async def test_duplicate_penalty(self, engine: RiskEngine, make_entity):
        """Same text duplicated → second occurrence penalised 30%."""
        r = await engine.assess("x", [
            make_entity("dup", EntityType.API_KEY),
            make_entity("dup", EntityType.API_KEY),
        ])
        assert r.score == 42  # 25 + 17
        assert r.details[0]["points"] == 25
        assert r.details[1]["points"] == 17

    async def test_triplicate_penalty(self, engine: RiskEngine, make_entity):
        """Third occurrence of same text also penalised."""
        r = await engine.assess("x", [
            make_entity("key", EntityType.API_KEY),
            make_entity("key", EntityType.API_KEY),
            make_entity("key", EntityType.API_KEY),
        ])
        # 25 + 17 + 17 = 59
        assert r.score == 59
        assert r.details[0]["points"] == 25
        assert r.details[1]["points"] == 17
        assert r.details[2]["points"] == 17

    async def test_mixed_levels_score(self, engine: RiskEngine, make_entity):
        """PERSON(5) + EMAIL(10) + BANK_ACCOUNT(15) = 30 → MEDIUM."""
        r = await engine.assess("x", [
            make_entity("alice", EntityType.PERSON),
            make_entity("a@b", EntityType.EMAIL),
            make_entity("123456", EntityType.BANK_ACCOUNT),
        ])
        assert r.score == 30.0
        assert r.level == RiskLevel.MEDIUM
        assert r.recommendation == "Review — consider masking sensitive fields"

    async def test_high_level(self, engine: RiskEngine, make_entity):
        """5 distinct PERSON (5×5=25) + 3 distinct EMAIL (3×10=30) = 55 → HIGH."""
        entities = [make_entity(f"p{i}", EntityType.PERSON) for i in range(5)]
        entities += [make_entity(f"e{i}@b", EntityType.EMAIL) for i in range(3)]
        r = await engine.assess("x", entities)
        assert r.score == 55.0
        assert r.level == RiskLevel.HIGH
        assert r.recommendation == "Review required — sensitive information detected"

    async def test_details_structure(self, engine: RiskEngine, make_entity):
        r = await engine.assess("x", [make_entity("alice", EntityType.PERSON)])
        assert len(r.details) == 1
        d = r.details[0]
        assert d["text"] == "alice"
        assert d["type"] == "PERSON"
        assert d["points"] == 5

    async def test_unknown_entity_type_yields_zero_points(self, engine: RiskEngine):
        """If an entity type isn't in any category, it contributes 0 points."""
        r = await engine.assess("x", [
            DetectedEntity(text="unknown", type="MADE_UP_TYPE", start=0, end=7, score=1.0),  # type: ignore[arg-type]
        ])
        assert r.score == 0.0
        assert r.level == RiskLevel.LOW
        assert r.details[0]["points"] == 0


# ── _level_exceeds_threshold ──────────────────────────────────────────────────

class TestThresholdComparison:
    def test_critical_exceeds_high(self):
        cfg = FilterConfig()
        cfg.risk.threshold = "high"
        eng = RiskEngine(cfg)
        assert eng._level_exceeds_threshold(RiskLevel.CRITICAL) is True

    def test_low_does_not_exceed_high(self):
        cfg = FilterConfig()
        cfg.risk.threshold = "high"
        eng = RiskEngine(cfg)
        assert eng._level_exceeds_threshold(RiskLevel.LOW) is False

    def test_equal_level_does_not_exceed(self):
        cfg = FilterConfig()
        cfg.risk.threshold = "medium"
        eng = RiskEngine(cfg)
        assert eng._level_exceeds_threshold(RiskLevel.MEDIUM) is False