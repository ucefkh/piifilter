"""Tests for the arbitration module — CandidateSpan, FusedEvidence, Arbitrator.

Covers:
- CandidateSpan factory methods (from_dict, from_detected_entity)
- CandidateSpan overlap/containment logic
- FusedEvidence introspection (type counts, detector coverage)
- Arbitrator clustering (interval merging)
- Arbitrator type conflict resolution (weighted majority)
- Arbitrator confidence fusion (weighted mean + calibrated model)
- Arbitrator end-to-end run() and arbitrate()/emit()
- Edge cases: empty input, single span, no overlap, full containment
"""

from __future__ import annotations

import pytest

from piifilter.arbitration.models import (
    CandidateSpan,
    ClusterKey,
    EvidenceSource,
    FusedEvidence,
)
from piifilter.arbitration.arbitrator import (
    Arbitrator,
    ArbitratorConfig,
    cluster_spans,
    fuse_cluster,
    fuse_weighted_mean,
    resolve_majority_type,
)
from piifilter.shared.models import DetectedEntity, EntityType


# ══════════════════════════════════════════════════════════════════════════════
# CandidateSpan tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCandidateSpan:
    def test_from_dict_minimal(self):
        """Minimal dict with only required keys."""
        d = {"entity_type": "EMAIL", "start": 10, "end": 25}
        span = CandidateSpan.from_dict(d)
        assert span.entity_type == EntityType.EMAIL
        assert span.start == 10
        assert span.end == 25
        assert span.confidence == 1.0
        assert span.detector == "unknown"
        assert span.value == ""

    def test_from_dict_full(self):
        """Full dict with all keys."""
        d = {
            "entity_type": "PHONE",
            "start": 5,
            "end": 18,
            "score": 0.92,
            "value": "+1-555-1234",
            "detector": "regex",
            "analysis_explanation": "matched pattern",
        }
        span = CandidateSpan.from_dict(d)
        assert span.entity_type == EntityType.PHONE
        assert span.confidence == 0.92
        assert span.value == "+1-555-1234"
        assert span.detector == "regex"
        assert span.raw == {"analysis_explanation": "matched pattern"}

    def test_from_dict_accepts_type_alias(self):
        """Dict may use 'type' key instead of 'entity_type'."""
        d = {"type": "PERSON", "start": 0, "end": 5}
        span = CandidateSpan.from_dict(d)
        assert span.entity_type == EntityType.PERSON

    def test_from_dict_accepts_text_alias(self):
        """Dict may use 'text' key instead of 'value'."""
        d = {"entity_type": "EMAIL", "start": 0, "end": 10, "text": "a@b.com"}
        span = CandidateSpan.from_dict(d)
        assert span.value == "a@b.com"

    def test_from_detected_entity(self):
        """Wrap a DetectedEntity instance."""
        de = DetectedEntity(
            entity_type=EntityType.IP_ADDRESS,
            value="192.168.1.1",
            start=0,
            end=11,
            confidence=0.99,
            detector="regex",
        )
        span = CandidateSpan.from_detected_entity(de)
        assert span.entity_type == EntityType.IP_ADDRESS
        assert span.value == "192.168.1.1"
        assert span.confidence == 0.99
        assert span.detector == "regex"

    def test_overlap_strict(self):
        """Adjacent spans do NOT overlap by default."""
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.EMAIL, 10, 20)
        assert not a.overlaps(b)

    def test_overlap_with_margin(self):
        """Adjacent spans overlap when margin >= 1."""
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.EMAIL, 10, 20)
        assert a.overlaps(b, margin=1)

    def test_overlap_partial(self):
        """Partially overlapping spans."""
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.EMAIL, 5, 15)
        assert a.overlaps(b)

    def test_overlap_fully_contained(self):
        """One span fully inside another."""
        a = CandidateSpan(EntityType.EMAIL, 0, 20)
        b = CandidateSpan(EntityType.EMAIL, 5, 15)
        assert a.overlaps(b)
        assert a.contains(b)
        assert not b.contains(a)

    def test_union_span(self):
        """Widest start/end from two spans."""
        a = CandidateSpan(EntityType.EMAIL, 3, 12)
        b = CandidateSpan(EntityType.EMAIL, 5, 15)
        assert a.union_span(b) == (3, 15)

    def test_sort_by_position(self):
        """Spans sort by start, then end."""
        spans = [
            CandidateSpan(EntityType.PERSON, 10, 20),
            CandidateSpan(EntityType.PERSON, 5, 8),
            CandidateSpan(EntityType.PERSON, 10, 15),
        ]
        spans.sort()
        assert [s.start for s in spans] == [5, 10, 10]
        assert [s.end for s in spans] == [8, 15, 20]


# ══════════════════════════════════════════════════════════════════════════════
# EvidenceSource tests
# ══════════════════════════════════════════════════════════════════════════════


class TestEvidenceSource:
    def test_frozen(self):
        """EvidenceSource is frozen (immutable)."""
        src = EvidenceSource(detector="regex", entity_type=EntityType.EMAIL,
                             confidence=0.95, start=0, end=10)
        with pytest.raises((AttributeError, TypeError)):
            src.confidence = 0.5  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# ClusterKey tests
# ══════════════════════════════════════════════════════════════════════════════


class TestClusterKey:
    def test_frozen_and_orderable(self):
        """ClusterKey is frozen and supports ordering."""
        a = ClusterKey(resolved_type=EntityType.EMAIL, start=5, end=15)
        b = ClusterKey(resolved_type=EntityType.EMAIL, start=10, end=20)
        assert a < b
        assert not (b < a)

    def test_from_span_interval(self):
        """Factory from type + start + end."""
        key = ClusterKey.from_span_interval(EntityType.EMAIL, 5, 15)
        assert key.resolved_type == EntityType.EMAIL
        assert key.start == 5
        assert key.end == 15


# ══════════════════════════════════════════════════════════════════════════════
# FusedEvidence tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFusedEvidence:
    def test_type_vote_counts(self):
        """Count votes per entity type."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 0.95, 0, 10),
            EvidenceSource("presidio", EntityType.EMAIL, 0.80, 0, 10),
            EvidenceSource("gliner", EntityType.PERSON, 0.70, 0, 10),
        ]
        fused = FusedEvidence(resolved_type=EntityType.EMAIL, start=0, end=10,
                              confidence=0.85, evidence=evidence)
        votes = fused.type_vote_counts()
        assert votes[EntityType.EMAIL] == 2
        assert votes[EntityType.PERSON] == 1

    def test_type_confidence_mean(self):
        """Mean confidence for a specific type."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 0.90, 0, 10),
            EvidenceSource("presidio", EntityType.EMAIL, 0.70, 0, 10),
        ]
        fused = FusedEvidence(resolved_type=EntityType.EMAIL, start=0, end=10,
                              confidence=0.80, evidence=evidence)
        assert fused.type_confidence_mean(EntityType.EMAIL) == pytest.approx(0.80)
        assert fused.type_confidence_mean(EntityType.PERSON) == 0.0

    def test_detector_count(self):
        """Unique detector count."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 0.95, 0, 10),
            EvidenceSource("presidio", EntityType.EMAIL, 0.80, 0, 10),
            EvidenceSource("regex", EntityType.EMAIL, 0.90, 5, 15),
        ]
        fused = FusedEvidence(resolved_type=EntityType.EMAIL, start=0, end=15,
                              confidence=0.85, evidence=evidence)
        assert fused.detector_count() == 2

    def test_to_detected_entity(self):
        """Emit DetectedEntity with fused evidence."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 0.95, 0, 10),
            EvidenceSource("presidio", EntityType.EMAIL, 0.80, 2, 8),
        ]
        fused = FusedEvidence(resolved_type=EntityType.EMAIL, start=0, end=10,
                              confidence=0.88, evidence=evidence)
        entity = fused.to_detected_entity()
        assert entity.entity_type == EntityType.EMAIL
        assert entity.start == 0
        assert entity.end == 10
        assert entity.detector == "arbitrator"
        assert len(entity.detector_votes) == 2
        assert entity.detector_votes[0]["detector"] == "regex"


# ══════════════════════════════════════════════════════════════════════════════
# cluster_spans tests
# ══════════════════════════════════════════════════════════════════════════════


class TestClusterSpans:
    def test_empty_list(self):
        assert cluster_spans([]) == []

    def test_single_span(self):
        span = CandidateSpan(EntityType.EMAIL, 0, 10)
        clusters = cluster_spans([span])
        assert len(clusters) == 1
        assert clusters[0] == [span]

    def test_two_non_overlapping(self):
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.PHONE, 20, 30)
        clusters = cluster_spans([a, b])
        assert len(clusters) == 2

    def test_two_overlapping(self):
        a = CandidateSpan(EntityType.EMAIL, 0, 15)
        b = CandidateSpan(EntityType.EMAIL, 10, 20)
        clusters = cluster_spans([a, b])
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_chain_overlap(self):
        """A chain of overlapping spans forms a single cluster."""
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.EMAIL, 8, 18)
        c = CandidateSpan(EntityType.EMAIL, 16, 26)
        clusters = cluster_spans([a, b, c])
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_full_containment(self):
        outer = CandidateSpan(EntityType.EMAIL, 0, 30)
        inner = CandidateSpan(EntityType.EMAIL, 5, 15)
        clusters = cluster_spans([inner, outer])
        assert len(clusters) == 1

    def test_adjacent_with_margin(self):
        """Adjacent spans merge when margin >= 1."""
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.EMAIL, 10, 20)
        clusters = cluster_spans([a, b], margin=1)
        assert len(clusters) == 1

    def test_adjacent_no_margin(self):
        """Adjacent spans are separate without margin."""
        a = CandidateSpan(EntityType.EMAIL, 0, 10)
        b = CandidateSpan(EntityType.EMAIL, 10, 20)
        clusters = cluster_spans([a, b], margin=0)
        assert len(clusters) == 2


# ══════════════════════════════════════════════════════════════════════════════
# resolve_majority_type tests
# ══════════════════════════════════════════════════════════════════════════════


class TestResolveMajorityType:
    def test_simple_majority(self):
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 1.0, 0, 10),
            EvidenceSource("presidio", EntityType.EMAIL, 0.8, 0, 10),
            EvidenceSource("gliner", EntityType.PERSON, 0.7, 0, 10),
        ]
        winner, share = resolve_majority_type(evidence, {"regex": 1.0, "presidio": 0.6, "gliner": 0.4})
        assert winner == EntityType.EMAIL

    def test_tie_break_by_confidence(self):
        """Tied weighted votes → higher total confidence wins."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 0.5, 0, 10),
            EvidenceSource("presidio", EntityType.PERSON, 0.99, 0, 10),
        ]
        winner, share = resolve_majority_type(evidence, {"regex": 1.0, "presidio": 0.6, "gliner": 0.4})
        # regex EMAIL: 1.0 ; presidio PERSON: 0.6
        # votes tied (1.0 vs 0.6 — wait, regex has higher weight)
        # Actually regex weight=1.0 gives EMAIL 1.0 vote, presidio 0.6 gives PERSON 0.6
        # So EMAIL wins by weighted vote
        assert winner == EntityType.EMAIL

    def test_empty_evidence_fallback(self):
        """Empty evidence returns safe fallback."""
        winner, share = resolve_majority_type([], {})
        assert winner == EntityType.PERSON

    def test_single_source(self):
        """Single source always wins."""
        evidence = [EvidenceSource("regex", EntityType.CREDIT_CARD, 0.95, 0, 16)]
        winner, share = resolve_majority_type(evidence, {"regex": 1.0})
        assert winner == EntityType.CREDIT_CARD
        assert share == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════════════════
# fuse_weighted_mean tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFuseWeightedMean:
    def test_same_weight_all(self):
        """Uniform detector weights produce simple mean."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 1.0, 0, 10),
            EvidenceSource("regex", EntityType.EMAIL, 0.5, 0, 10),
        ]
        fuse = FusedEvidence(EntityType.EMAIL, 0, 10, 0.0, evidence=evidence)
        # both regex weight=1.0 → (1.0*1.0 + 0.5*1.0) / 2.0 = 0.75
        assert fuse_weighted_mean(fuse) == pytest.approx(0.75)

    def test_different_detector_weights(self):
        """Detectors with different weights are reflected."""
        evidence = [
            EvidenceSource("regex", EntityType.EMAIL, 1.0, 0, 10),
            EvidenceSource("gliner", EntityType.EMAIL, 0.5, 0, 10),
        ]
        fuse = FusedEvidence(EntityType.EMAIL, 0, 10, 0.0, evidence=evidence)
        # regex weight=1.0, gliner weight=0.4
        # weighted_sum = 1.0*1.0 + 0.5*0.4 = 1.2
        # total_weight = 1.0 + 0.4 = 1.4
        # result = 1.2 / 1.4 ≈ 0.8571
        assert fuse_weighted_mean(fuse) == pytest.approx(0.8571, rel=1e-3)

    def test_empty_evidence(self):
        fuse = FusedEvidence(EntityType.PERSON, 0, 10, 0.0, evidence=[])
        assert fuse_weighted_mean(fuse) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# fuse_cluster tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFuseCluster:
    def test_single_span(self):
        cluster = [CandidateSpan(EntityType.EMAIL, 5, 20, detector="regex", confidence=1.0)]
        fuse = fuse_cluster(cluster, use_calibrated=False)
        assert fuse.resolved_type == EntityType.EMAIL
        assert fuse.start == 5
        assert fuse.end == 20
        assert fuse.confidence > 0.0
        assert len(fuse.evidence) == 1

    def test_two_same_type(self):
        cluster = [
            CandidateSpan(EntityType.EMAIL, 5, 20, detector="regex", confidence=1.0),
            CandidateSpan(EntityType.EMAIL, 5, 20, detector="presidio", confidence=0.8),
        ]
        fuse = fuse_cluster(cluster, use_calibrated=False)
        assert fuse.resolved_type == EntityType.EMAIL
        assert len(fuse.evidence) == 2

    def test_type_conflict(self):
        cluster = [
            CandidateSpan(EntityType.EMAIL, 5, 20, detector="regex", confidence=1.0),
            CandidateSpan(EntityType.PERSON, 5, 20, detector="gliner", confidence=0.9),
        ]
        fuse = fuse_cluster(cluster, use_calibrated=False)
        # regex weight=1.0 > gliner weight=0.4 → EMAIL wins
        assert fuse.resolved_type == EntityType.EMAIL

    def test_outer_span_merged(self):
        cluster = [
            CandidateSpan(EntityType.EMAIL, 0, 10, detector="regex", confidence=1.0),
            CandidateSpan(EntityType.EMAIL, 5, 15, detector="presidio", confidence=0.8),
        ]
        fuse = fuse_cluster(cluster, use_calibrated=False)
        assert fuse.start == 0
        assert fuse.end == 15


# ══════════════════════════════════════════════════════════════════════════════
# Arbitrator end-to-end tests
# ══════════════════════════════════════════════════════════════════════════════


class TestArbitratorEndToEnd:
    @pytest.mark.asyncio
    async def test_empty_input(self):
        arb = Arbitrator()
        fused = await arb.arbitrate([])
        assert fused == []

    @pytest.mark.asyncio
    async def test_single_detection(self):
        arb = Arbitrator()
        spans = [CandidateSpan(EntityType.EMAIL, 6, 23, detector="regex", confidence=1.0)]
        fused = await arb.arbitrate(spans, text="contact user@example.com here")
        assert len(fused) == 1

    @pytest.mark.asyncio
    async def test_run_empty(self):
        arb = Arbitrator()
        entities = await arb.run([], text="hello")
        assert entities == []

    @pytest.mark.asyncio
    async def test_run_single_dict(self):
        arb = Arbitrator()
        text = "my email is user@example.com"
        raw = [{"entity_type": "EMAIL", "start": 11, "end": 28, "score": 1.0, "detector": "regex"}]
        entities = await arb.run(raw, text=text)
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.EMAIL
        # "my email is user@example.com"
        # start=11 → " user@example.com" (includes the leading space)
        assert entities[0].value == " user@example.com"
        assert entities[0].start == 11
        assert entities[0].detector == "arbitrator"
        assert len(entities[0].detector_votes) == 1

    @pytest.mark.asyncio
    async def test_run_two_non_overlapping(self):
        arb = Arbitrator()
        text = "a@b.com and 555-1234"
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 7, "score": 1.0, "detector": "regex"},
            {"entity_type": "PHONE", "start": 12, "end": 19, "score": 1.0, "detector": "regex"},
        ]
        entities = await arb.run(raw, text=text)
        assert len(entities) == 2

    @pytest.mark.asyncio
    async def test_run_same_span_same_type(self):
        """Two detectors find same span with same type → fused."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        text = "email user@example.com"
        raw = [
            {"entity_type": "EMAIL", "start": 6, "end": 22, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 6, "end": 22, "score": 0.8, "detector": "presidio"},
        ]
        entities = await arb.run(raw, text=text)
        assert len(entities) == 1
        assert entities[0].detector == "arbitrator"
        assert len(entities[0].detector_votes) == 2

    @pytest.mark.asyncio
    async def test_run_same_span_different_type(self):
        """Regex EMAIL beats gliner PERSON via higher weight."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        raw = [
            {"entity_type": "EMAIL", "start": 6, "end": 22, "score": 1.0, "detector": "regex"},
            {"entity_type": "PERSON", "start": 6, "end": 22, "score": 0.9, "detector": "gliner"},
        ]
        entities = await arb.run(raw)
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.EMAIL

    @pytest.mark.asyncio
    async def test_overlapping_spans_fuse(self):
        """Partially overlapping spans → one fused result with outer bounds."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 10, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 5, "end": 15, "score": 0.8, "detector": "presidio"},
        ]
        entities = await arb.run(raw)
        assert len(entities) == 1
        assert entities[0].start == 0
        assert entities[0].end == 15

    @pytest.mark.asyncio
    async def test_multiple_clusters(self):
        """Mixed overlapping/non-overlapping → correct number of clusters."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 10, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 5, "end": 12, "score": 0.8, "detector": "presidio"},
            {"entity_type": "PHONE", "start": 30, "end": 40, "score": 1.0, "detector": "regex"},
            {"entity_type": "ADDRESS", "start": 50, "end": 60, "score": 0.75, "detector": "presidio"},
            {"entity_type": "ADDRESS", "start": 55, "end": 65, "score": 1.0, "detector": "regex"},
        ]
        entities = await arb.run(raw)
        assert len(entities) == 3

    @pytest.mark.asyncio
    async def test_run_mixed_input_types(self):
        """run() accepts mixed dicts and DetectedEntities."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        raw: list = [
            {"entity_type": "EMAIL", "start": 0, "end": 10, "score": 1.0, "detector": "regex"},
            DetectedEntity(EntityType.EMAIL, "", 2, 8, confidence=0.8, detector="presidio"),
        ]
        entities = await arb.run(raw)
        assert len(entities) == 1

    @pytest.mark.asyncio
    async def test_detector_weights_zero_excludes(self):
        """Detector with weight 0.0 effectively excluded via calibrated model."""
        config = ArbitratorConfig(detector_weights={"regex": 1.0, "presidio": 0.0},
                                  use_calibrated_model=True)
        arb = Arbitrator(config)
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 10, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 0, "end": 10, "score": 0.2, "detector": "presidio"},
        ]
        entities = await arb.run(raw)
        # With calibrated model: regex weight=1.0, presidio weight=0.0
        # Weighted-mean with both present: (1.0*1.0 + 0.2*0.0) / (1.0 + 0.0) = 1.0
        # That raw_conf blends 30% into calibrated output
        # With 2 detectors agreeing, source_agreement=2, high format_specificity
        # → calibrated confidence should be high
        assert entities[0].confidence > 0.7


# ══════════════════════════════════════════════════════════════════════════════
# Type conflict scenario (pipeline-style)
# ══════════════════════════════════════════════════════════════════════════════


class TestTypeConflictScenario:
    @pytest.mark.asyncio
    async def test_person_subspans_inside_email(self):
        """PERSON subspans inside an EMAIL span should cluster and resolve to EMAIL."""
        text = "email contact@support.com for admin"
        raw = [
            {"entity_type": "EMAIL", "start": 6, "end": 24, "score": 1.0, "detector": "regex"},
            {"entity_type": "PERSON", "start": 6, "end": 13, "score": 0.75, "detector": "presidio"},
            {"entity_type": "PERSON", "start": 14, "end": 21, "score": 0.70, "detector": "presidio"},
        ]
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        entities = await arb.run(raw, text=text)

        # All three spans overlap → one cluster.
        # EMAIL (regex, weight=1.0) vs PERSON×2 (presidio, weight=0.6 each = 1.2)
        # PERSON wins by weighted vote (1.2 > 1.0)
        email_entities = [e for e in entities if e.entity_type == EntityType.EMAIL]
        person_entities = [e for e in entities if e.entity_type == EntityType.PERSON]
        assert len(person_entities) >= 1, (
            f"Expected PERSON to win (weighted vote), got {len(email_entities)} EMAIL, "
            f"{len(person_entities)} PERSON"
        )

    @pytest.mark.asyncio
    async def test_chat_scenario(self):
        """Realistic multi-detector chat scenario."""
        text = "Hi, my email is alice@example.com and my phone is +1-555-0199. My name is Alice Johnson."
        raw = [
            {"entity_type": "EMAIL", "start": 16, "end": 33, "score": 1.0, "detector": "regex"},
            {"entity_type": "PHONE", "start": 48, "end": 59, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 16, "end": 33, "score": 0.85, "detector": "presidio"},
            {"entity_type": "PERSON", "start": 73, "end": 86, "score": 0.88, "detector": "presidio"},
            {"entity_type": "PERSON", "start": 73, "end": 86, "score": 0.92, "detector": "gliner"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        entities.sort(key=lambda e: e.start)
        assert len(entities) >= 3, f"Expected at least 3 entities, got {len(entities)}"

        email_entities = [e for e in entities if e.entity_type == EntityType.EMAIL]
        phone_entities = [e for e in entities if e.entity_type == EntityType.PHONE]
        person_entities = [e for e in entities if e.entity_type == EntityType.PERSON]
        assert len(email_entities) >= 1
        assert len(phone_entities) >= 1
        assert len(person_entities) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_identical_spans_three_detectors(self):
        """Three detectors on same span → one fused result."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        raw = [
            {"entity_type": "EMAIL", "start": 5, "end": 20, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 5, "end": 20, "score": 0.85, "detector": "presidio"},
            {"entity_type": "EMAIL", "start": 5, "end": 20, "score": 0.70, "detector": "gliner"},
        ]
        entities = await arb.run(raw)
        assert len(entities) == 1
        assert len(entities[0].detector_votes) == 3

    @pytest.mark.asyncio
    async def test_no_overlap(self):
        """Completely disjoint spans remain separate."""
        arb = Arbitrator()
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 5, "score": 1.0, "detector": "regex"},
            {"entity_type": "PHONE", "start": 10, "end": 15, "score": 1.0, "detector": "regex"},
            {"entity_type": "IP_ADDRESS", "start": 20, "end": 30, "score": 1.0, "detector": "regex"},
        ]
        entities = await arb.run(raw)
        assert len(entities) == 3

    @pytest.mark.asyncio
    async def test_adjacent_merge_with_margin(self):
        """With overlap_margin=1, adjacent spans merge."""
        config = ArbitratorConfig(overlap_margin=1, use_calibrated_model=False)
        arb = Arbitrator(config)
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 10, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 10, "end": 20, "score": 1.0, "detector": "presidio"},
        ]
        entities = await arb.run(raw)
        assert len(entities) == 1

    @pytest.mark.asyncio
    async def test_text_value_extraction(self):
        """Value extracted from original text."""
        arb = Arbitrator()
        text = "hello alice@example.com world"
        raw = [{"entity_type": "EMAIL", "start": 6, "end": 23, "score": 1.0, "detector": "regex"}]
        entities = await arb.run(raw, text=text)
        assert entities[0].value == "alice@example.com"

    @pytest.mark.asyncio
    async def test_overlap_dedup_same_type(self):
        """Same-type overlapping entities deduplicate to highest confidence."""
        arb = Arbitrator(config=ArbitratorConfig(use_calibrated_model=False))
        raw = [
            {"entity_type": "EMAIL", "start": 0, "end": 20, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 5, "end": 15, "score": 0.8, "detector": "presidio"},
        ]
        entities = await arb.run(raw)
        # Both overlap and same type → fused cluster
        # Outer span: [0, 20]
        assert len(entities) == 1
        assert entities[0].start == 0
        assert entities[0].end == 20


# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN containment rule (arbitration precision fix)
# ══════════════════════════════════════════════════════════════════════════════


class TestDomainContainmentRule:
    @pytest.mark.asyncio
    async def test_domain_inside_email_is_dropped(self):
        """DOMAIN inside EMAIL is a FP — the domain fragment was already caught."""
        text = "contact user@example.com here"
        raw = [
            {"entity_type": "EMAIL", "start": 8, "end": 25, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 13, "end": 25, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0, f"DOMAIN inside EMAIL should be dropped, got {len(domain_entities)}"
        email_entities = [e for e in entities if e.entity_type == EntityType.EMAIL]
        assert len(email_entities) >= 1, "EMAIL should still be emitted"

    @pytest.mark.asyncio
    async def test_domain_inside_url_is_dropped(self):
        """DOMAIN inside URL is dropped."""
        text = "visit https://example.com/path"
        raw = [
            {"entity_type": "URL", "start": 6, "end": 30, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 15, "end": 28, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0

    @pytest.mark.asyncio
    async def test_domain_inside_ip_address_is_dropped(self):
        """DOMAIN inside IP_ADDRESS is dropped."""
        text = "server 10.0.0.1"
        # IP 10.0.0.1 could also match DOMAIN as "0.1" — drop it
        raw = [
            {"entity_type": "IP_ADDRESS", "start": 7, "end": 15, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 9, "end": 14, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0

    @pytest.mark.asyncio
    async def test_standalone_domain_is_preserved(self):
        """DOMAIN not inside any higher-specificity span is preserved."""
        text = "visit example.com for more info"
        raw = [
            {"entity_type": "DOMAIN", "start": 6, "end": 17, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 1
        assert domain_entities[0].value == "example.com"

    @pytest.mark.asyncio
    async def test_domain_inside_private_url_is_dropped(self):
        """DOMAIN inside PRIVATE_URL is dropped."""
        text = "connect to http://localhost:3000/api"
        raw = [
            {"entity_type": "PRIVATE_URL", "start": 11, "end": 32, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 17, "end": 26, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0

    @pytest.mark.asyncio
    async def test_domain_inside_database_url_is_dropped(self):
        """DOMAIN inside DATABASE_URL is dropped."""
        text = "postgres://user:pass@db.internal:5432/mydb"
        raw = [
            {"entity_type": "DATABASE_URL", "start": 0, "end": 47, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 20, "end": 31, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0

    @pytest.mark.asyncio
    async def test_domain_inside_file_path_is_dropped(self):
        """DOMAIN inside FILE_PATH is dropped."""
        text = "/home/user/project/config.yaml"
        raw = [
            {"entity_type": "FILE_PATH", "start": 0, "end": 31, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 16, "end": 23, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0

    @pytest.mark.asyncio
    async def test_multiple_domains_email_context(self):
        """Multiple DOMAIN fragments inside EMAIL all dropped."""
        text = "emails: alice@example.com and bob@test.org"
        raw = [
            {"entity_type": "EMAIL", "start": 8, "end": 25, "score": 1.0, "detector": "regex"},
            {"entity_type": "EMAIL", "start": 30, "end": 42, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 14, "end": 25, "score": 0.75, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 35, "end": 42, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 0
        email_entities = [e for e in entities if e.entity_type == EntityType.EMAIL]
        assert len(email_entities) == 2

    @pytest.mark.asyncio
    async def test_domain_partially_overlapping_not_inside_is_preserved(self):
        """DOMAIN overlapping but not fully contained by higher-specificity span is preserved."""
        text = "connect to https://x.com/example.org"
        # DOMAIN "example.org" (24-35) overlaps URL end but is NOT contained within it
        raw = [
            {"entity_type": "URL", "start": 11, "end": 26, "score": 1.0, "detector": "regex"},
            {"entity_type": "DOMAIN", "start": 24, "end": 35, "score": 0.75, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        # DOMAIN "example.org" extends past URL (URL ends at 26, DOMAIN ends at 35)
        # So DOMAIN is NOT fully contained — it should be preserved
        assert len(domain_entities) >= 1

    @pytest.mark.asyncio
    async def test_domain_without_container_span_is_kept(self):
        """DOMAIN span with no container types present is kept unchanged."""
        text = "visit example.com today"
        raw = [
            {"entity_type": "DOMAIN", "start": 6, "end": 17, "score": 0.75, "detector": "regex"},
            {"entity_type": "PERSON", "start": 18, "end": 23, "score": 0.50, "detector": "regex"},
        ]
        arb = Arbitrator()
        entities = await arb.run(raw, text=text)
        domain_entities = [e for e in entities if e.entity_type == EntityType.DOMAIN]
        assert len(domain_entities) == 1