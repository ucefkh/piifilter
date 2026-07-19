"""Integration tests for max(raw, pipeline) merge — pipeline_mode UNION behavior.

Tests that the pipeline never loses regex entities even when other detectors
produce overlapping results that would normally be deduplicated away.
"""
from __future__ import annotations

import pytest

from piifilter.pipeline import FilterPipeline, _entity_detector, _entity_span
from piifilter.config import FilterConfig, DetectionConfig
from piifilter.session import Session
from piifilter.registry.registry import PluginRegistry
from piifilter.events.bus import EventBus
from piifilter.shared.models import DetectedEntity, EntityType
from piifilter.interfaces.detector import Detector


# ── Mock detectors ──────────────────────────────────────────────────────


class MockRegexDetector(Detector):
    """Simulates regex detector — returns specific entities."""

    def __init__(self, entities: list[dict]):
        self._entities = entities

    @property
    def name(self) -> str:
        return "regex"

    async def detect(self, text: str, **kw) -> list[dict]:
        return self._entities

    async def initialize(self) -> None: ...
    async def shutdown(self) -> None: ...


class MockPresidioDetector(Detector):
    """Simulates presidio detector — returns broader overlapping entities."""

    def __init__(self, entities: list[dict]):
        self._entities = entities

    @property
    def name(self) -> str:
        return "presidio"

    async def detect(self, text: str, **kw) -> list[dict]:
        return self._entities

    async def initialize(self) -> None: ...
    async def shutdown(self) -> None: ...


# ── Fixtures ────────────────────────────────────────────────────────────


def make_pipeline(registry, pipeline_mode: bool = True):
    config = FilterConfig(detection=DetectionConfig(pipeline_mode=pipeline_mode))
    return FilterPipeline(config=config, registry=registry, event_bus=EventBus())


def extract_entities(session: Session) -> list[tuple[int, int, str, str]]:
    """Return (start, end, type, detector) tuples, handling both dict and object shapes."""
    result = []
    for e in session.entities:
        if isinstance(e, dict):
            result.append((e.get("start"), e.get("end"), e.get("entity_type"), e.get("detector")))
        else:
            result.append((e.start, e.end, e.type.value, e.detector))
    return result


# ── Tests: max merge preserves regex entities ───────────────────────────


@pytest.mark.asyncio
async def test_max_merge_preserves_regex_email_when_presidio_overlaps():
    """Regex EMAIL at [5,20] should survive even if presidio PERSON covers [0,30]."""
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "EMAIL", "start": 5, "end": 20, "value": "user@example.com",
         "score": 0.9, "detector": "regex"},
    ]))
    reg.register_detector(MockPresidioDetector([
        {"entity_type": "PERSON", "start": 0, "end": 30, "value": "User user@example.com",
         "score": 0.85, "detector": "presidio"},
    ]))

    pipeline = make_pipeline(reg)
    session = Session(prompt="User user@example.com", config=pipeline.config)
    session = await pipeline._detect(session)

    entities = extract_entities(session)
    assert (5, 20, "EMAIL", "regex") in entities, \
        f"Regex EMAIL was lost during pipeline dedup! Entities: {entities}"
    # NOTE: presidio PERSON at [0,30] is suppressed by cross-type suppression
    # (PERSON overlapping EMAIL → suppressed). This is existing correct behavior.
    # The key assertion: regex EMAIL survived.

@pytest.mark.asyncio
async def test_max_merge_preserves_regex_phone_when_presidio_person_overlaps():
    """Regex PHONE at [10,24] should survive even if presidio PERSON covers [5,30]."""
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "PHONE", "start": 10, "end": 24, "value": "+1-555-123-4567",
         "score": 0.9, "detector": "regex"},
    ]))
    reg.register_detector(MockPresidioDetector([
        {"entity_type": "PERSON", "start": 5, "end": 30,
         "value": "Name +1-555-123-4567", "score": 0.85, "detector": "presidio"},
    ]))

    pipeline = make_pipeline(reg)
    session = Session(prompt="Name +1-555-123-4567", config=pipeline.config)
    session = await pipeline._detect(session)

    entities = extract_entities(session)
    assert (10, 24, "PHONE", "regex") in entities, \
        f"Regex PHONE was lost! Entities: {entities}"


@pytest.mark.asyncio
async def test_max_merge_preserves_multiple_regex_matches():
    """Multiple regex entities should all survive pipeline dedup."""
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "EMAIL", "start": 10, "end": 25, "value": "a@b.com",
         "score": 0.9, "detector": "regex"},
        {"entity_type": "IP_ADDRESS", "start": 40, "end": 53, "value": "192.168.1.1",
         "score": 0.9, "detector": "regex"},
    ]))
    reg.register_detector(MockPresidioDetector([
        {"entity_type": "PERSON", "start": 0, "end": 60,
         "value": "Contact a@b.com from 192.168.1.1",
         "score": 0.85, "detector": "presidio"},
    ]))

    pipeline = make_pipeline(reg)
    session = Session(prompt="Contact a@b.com from 192.168.1.1", config=pipeline.config)
    session = await pipeline._detect(session)

    entities = extract_entities(session)
    assert (10, 25, "EMAIL", "regex") in entities, f"Regex EMAIL lost! {entities}"
    assert (40, 53, "IP_ADDRESS", "regex") in entities, f"Regex IP lost! {entities}"


@pytest.mark.asyncio
async def test_max_merge_can_be_disabled():
    """When pipeline_mode=False, regex entities CAN be suppressed by dedup.

    Scenario: a regex PERSON detection overlaps a structural entity type (EMAIL).
    The cross-type suppression at line 303-314 suppresses PERSON when it overlaps
    with structural types.  With pipeline_mode=True, the regex PERSON is re-added.
    With pipeline_mode=False, it stays suppressed.
    """
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "EMAIL", "start": 0, "end": 30,
         "value": "Contact: alice@example.com", "score": 0.9, "detector": "regex"},
        # A regex PERSON that overlaps with the EMAIL span — cross-type suppression
        # will suppress it since PERSON overlaps FILE_PATH_URL_EMAIL... etc
        {"entity_type": "PERSON", "start": 10, "end": 25,
         "value": "alice@example.co", "score": 0.9, "detector": "regex"},
    ]))

    # With pipeline_mode=False, regex PERSON gets suppressed by cross-type suppression
    pipeline = make_pipeline(reg, pipeline_mode=False)
    session = Session(prompt="Contact: alice@example.com", config=pipeline.config)
    session = await pipeline._detect(session)

    # Only EMAIL survives (PERSON suppressed by cross-type)
    types = sorted(e.get("entity_type") if isinstance(e, dict) else e.type.value
                   for e in session.entities)
    assert types == ["EMAIL"], f"Expected only EMAIL, got {types}"


@pytest.mark.asyncio
async def test_max_merge_reenables_suppressed_regex_entity():
    """With pipeline_mode=True, regex entities suppressed by cross-type rules are re-added.

    Scenario: regex PERSON overlaps with regex EMAIL — cross-type suppression drops
    the PERSON.  With pipeline_mode=True, the raw regex PERSON is merged back.
    """
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "EMAIL", "start": 0, "end": 30,
         "value": "Contact: alice@example.com", "score": 0.9, "detector": "regex"},
        {"entity_type": "PERSON", "start": 10, "end": 25,
         "value": "alice@example.co", "score": 0.9, "detector": "regex"},
    ]))

    pipeline = make_pipeline(reg, pipeline_mode=True)
    session = Session(prompt="Contact: alice@example.com", config=pipeline.config)
    session = await pipeline._detect(session)

    entities = extract_entities(session)
    # Both EMAIL and PERSON should survive with pipeline_mode=True
    types = sorted(e[2] for e in entities)
    assert "EMAIL" in types, f"EMAIL lost: {entities}"
    assert "PERSON" in types, f"PERSON lost by cross-type suppression but should be re-added! Entities: {entities}"


@pytest.mark.asyncio
async def test_max_merge_exact_duplicate_not_readded():
    """If a regex entity survived dedup naturally, it should not be duplicated."""
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "EMAIL", "start": 5, "end": 20, "value": "user@example.com",
         "score": 0.9, "detector": "regex"},
    ]))
    # Lower-score presidio EMAIL inside regex span — will be suppressed by priority dedup
    reg.register_detector(MockPresidioDetector([
        {"entity_type": "EMAIL", "start": 10, "end": 15, "value": "user@exa",
         "score": 0.5, "detector": "presidio"},
    ]))

    pipeline = make_pipeline(reg)
    session = Session(prompt="Contact user@example.com", config=pipeline.config)
    session = await pipeline._detect(session)

    # Regex EMAIL [5,20] should survive naturally (higher priority, contains presidio)
    assert len(session.entities) == 1, f"Expected 1 entity, got {len(session.entities)}"
    e = session.entities[0]
    detector = e.get("detector") if isinstance(e, dict) else e.detector
    assert detector == "regex"


@pytest.mark.asyncio
async def test_max_merge_different_types_both_survive():
    """Regex EMAIL and presidio ADDRESS at different positions should both survive."""
    reg = PluginRegistry()
    reg.register_detector(MockRegexDetector([
        {"entity_type": "EMAIL", "start": 10, "end": 24, "value": "test@test.com",
         "score": 0.9, "detector": "regex"},
    ]))
    reg.register_detector(MockPresidioDetector([
        {"entity_type": "ADDRESS", "start": 30, "end": 50,
         "value": "123 Main St, City",
         "score": 0.85, "detector": "presidio"},
    ]))

    pipeline = make_pipeline(reg)
    session = Session(prompt="Email test@test.com at 123 Main St, City", config=pipeline.config)
    session = await pipeline._detect(session)

    assert len(session.entities) == 2, f"Expected 2 entities, got {len(session.entities)}"
    entities = extract_entities(session)
    assert (10, 24, "EMAIL", "regex") in entities
    assert (30, 50, "ADDRESS", "presidio") in entities


@pytest.mark.asyncio
async def test_max_merge_no_detectors_returns_empty():
    """No detectors registered should return empty entities regardless of pipeline_mode."""
    reg = PluginRegistry()

    for mode in [True, False]:
        pipeline = make_pipeline(reg, pipeline_mode=mode)
        session = Session(prompt="Hello world", config=pipeline.config)
        session = await pipeline._detect(session)
        assert session.entities == [], f"Expected empty entities for mode={mode}, got {session.entities}"


@pytest.mark.asyncio
async def test_max_merge_only_presidio_works_normally():
    """When there are no regex entities, pipeline_mode has no effect."""
    reg = PluginRegistry()
    reg.register_detector(MockPresidioDetector([
        {"entity_type": "EMAIL", "start": 0, "end": 10, "value": "a@b.com",
         "score": 0.8, "detector": "presidio"},
    ]))

    for mode in [True, False]:
        pipeline = make_pipeline(reg, pipeline_mode=mode)
        session = Session(prompt="a@b.com", config=pipeline.config)
        session = await pipeline._detect(session)
        assert len(session.entities) == 1, f"Expected 1 entity for mode={mode}"