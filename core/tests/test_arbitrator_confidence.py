"""Tests for the Arbitrator's calibrated confidence model.

Tests cover:
- Logistic regression score calibration
- Feature extraction from cluster evidence
- End-to-end arbitration pipeline (cluster → fuse → emit)
- Weighted majority type resolution
- Confidence values in expected ranges
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core" / "src"))

from piifilter.arbitration.arbitrator import (
    Arbitrator,
    ArbitratorConfig,
    _calibrated_confidence,
    _compute_cluster_features,
    cluster_spans,
    fuse_cluster,
    fuse_weighted_mean,
    resolve_majority_type,
)
from piifilter.arbitration.models import (
    CandidateSpan,
    EvidenceSource,
    FusedEvidence,
)
from piifilter.shared.models import DetectedEntity, EntityType


# ═══════════════════════════════════════════════════════════════════════════════
# LOGISTIC REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


def test_calibrated_confidence_monotonic():
    """Calibrated confidence should be monotonic in each feature."""
    base = dict(
        source_agreement_count=1,
        checksum_valid=False,
        left_context_keyword=False,
        format_specificity=0.5,
        length_prior=0.2,
    )
    base_score = _calibrated_confidence(**base)

    # More agreement = higher score
    higher_agreement = dict(base, source_agreement_count=3)
    assert _calibrated_confidence(**higher_agreement) >= base_score

    # Checksum valid = higher score
    with_checksum = dict(base, checksum_valid=True)
    assert _calibrated_confidence(**with_checksum) >= base_score

    # Context keyword = higher score
    with_context = dict(base, left_context_keyword=True)
    assert _calibrated_confidence(**with_context) >= base_score

    # Higher specificity = higher score
    higher_spec = dict(base, format_specificity=0.9)
    assert _calibrated_confidence(**higher_spec) >= base_score

    # Longer length = higher score
    longer = dict(base, length_prior=0.4)
    assert _calibrated_confidence(**longer) >= base_score


def test_calibrated_confidence_range():
    """All outputs must be in [0, 1]."""
    test_cases = [
        dict(source_agreement_count=0, checksum_valid=False,
             left_context_keyword=False, format_specificity=0.0,
             length_prior=0.0),
        dict(source_agreement_count=5, checksum_valid=True,
             left_context_keyword=True, format_specificity=1.0,
             length_prior=1.0),
        dict(source_agreement_count=2, checksum_valid=False,
             left_context_keyword=True, format_specificity=0.75,
             length_prior=0.3),
    ]
    for tc in test_cases:
        score = _calibrated_confidence(**tc)
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for {tc}"
    print("  Range check: all scores in [0, 1] ✓")


def test_calibrated_confidence_high_confidence():
    """Strong signals should produce high confidence."""
    score = _calibrated_confidence(
        source_agreement_count=3,
        checksum_valid=True,
        left_context_keyword=True,
        format_specificity=0.95,
        length_prior=0.4,
    )
    assert score > 0.85, f"Expected high confidence, got {score:.4f}"
    print(f"  High-confidence case: {score:.4f} ✓")


def test_calibrated_confidence_low_confidence():
    """Weak signals should produce low confidence."""
    score = _calibrated_confidence(
        source_agreement_count=1,
        checksum_valid=False,
        left_context_keyword=False,
        format_specificity=0.35,
        length_prior=0.1,
    )
    assert score < 0.37, f"Expected low confidence, got {score:.4f}"
    print(f"  Low-confidence case: {score:.4f} ✓")


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


def test_feature_extraction_cc_with_context():
    """Credit card with context keyword should detect left_context_keyword."""
    text = "Please process this credit card: 4111-1111-1111-1111"
    src = EvidenceSource(
        detector="regex",
        entity_type=EntityType.CREDIT_CARD,
        confidence=0.92,
        start=34,
        end=53,
        raw={"checksum_valid": True},
    )
    fuse = FusedEvidence(
        resolved_type=EntityType.CREDIT_CARD,
        start=34,
        end=53,
        confidence=0.92,
        evidence=[src],
    )
    features = _compute_cluster_features(fuse, text=text)
    assert features["checksum_valid"] is True
    assert features["left_context_keyword"] is True
    assert features["format_specificity"] == 0.95
    assert features["length_prior"] > 0.0
    print(f"  CC features: {features} ✓")


def test_feature_extraction_no_context():
    """Plain text without context keywords should not flag."""
    text = "The quick brown fox jumps over 192.168.1.1"
    src = EvidenceSource(
        detector="regex",
        entity_type=EntityType.IP_ADDRESS,
        confidence=0.85,
        start=40,
        end=51,
        raw={},
    )
    fuse = FusedEvidence(
        resolved_type=EntityType.IP_ADDRESS,
        start=40,
        end=51,
        confidence=0.85,
        evidence=[src],
    )
    features = _compute_cluster_features(fuse, text=text)
    assert features["checksum_valid"] is False
    assert features["left_context_keyword"] is False
    print(f"  No-context features: {features} ✓")


# ═══════════════════════════════════════════════════════════════════════════════
# CLUSTERING TESTS
# ═══════════════════════════════════════════════════════════════════════════════


def test_cluster_overlapping_spans():
    """Overlapping spans should be grouped into one cluster."""
    spans = [
        CandidateSpan(
            entity_type=EntityType.CREDIT_CARD, start=10, end=30,
            confidence=0.9, detector="regex",
            value="4111-1111-1111-1111",
        ),
        CandidateSpan(
            entity_type=EntityType.CREDIT_CARD, start=12, end=30,
            confidence=0.7, detector="presidio",
            value="1111-1111-1111",
        ),
        CandidateSpan(
            entity_type=EntityType.EMAIL, start=50, end=70,
            confidence=0.9, detector="regex",
            value="user@example.com",
        ),
    ]
    clusters = cluster_spans(spans)
    assert len(clusters) == 2, f"Expected 2 clusters, got {len(clusters)}"
    assert len(clusters[0]) == 2, "First cluster should have 2 spans"
    assert len(clusters[1]) == 1, "Second cluster should have 1 span"
    print(f"  Clusters: {len(clusters)} groups ✓")


def test_cluster_non_overlapping_spans():
    """Non-overlapping spans should form separate clusters."""
    spans = [
        CandidateSpan(
            entity_type=EntityType.EMAIL, start=0, end=20,
            confidence=0.9, detector="regex",
            value="user@example.com",
        ),
        CandidateSpan(
            entity_type=EntityType.PHONE, start=50, end=72,
            confidence=0.85, detector="regex",
            value="+1-555-123-4567",
        ),
    ]
    clusters = cluster_spans(spans)
    assert len(clusters) == 2
    print(f"  Non-overlapping: {len(clusters)} clusters ✓")


# ═══════════════════════════════════════════════════════════════════════════════
# FUSION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


def test_fuse_single_detector():
    """Single detector should produce calibrated confidence."""
    spans = [
        CandidateSpan(
            entity_type=EntityType.EMAIL, start=0, end=16,
            confidence=0.9, detector="regex",
            value="user@example.com",
            raw={},
        ),
    ]
    text = "Email: user@example.com"
    fuse = fuse_cluster(spans, text=text, use_calibrated=True)
    assert fuse.resolved_type == EntityType.EMAIL
    assert 0.4 <= fuse.confidence <= 1.0
    assert len(fuse.evidence) == 1
    print(f"  Single detector fused: {fuse.resolved_type.value} "
          f"confidence={fuse.confidence:.4f} ✓")


def test_fuse_multi_detector_agreement():
    """Multiple detectors agreeing should boost confidence."""
    spans = [
        CandidateSpan(
            entity_type=EntityType.CREDIT_CARD, start=10, end=29,
            confidence=0.92, detector="regex",
            value="4111-1111-1111-1111",
            raw={"checksum_valid": True},
        ),
        CandidateSpan(
            entity_type=EntityType.CREDIT_CARD, start=10, end=29,
            confidence=0.80, detector="presidio",
            value="4111-1111-1111-1111",
            raw={},
        ),
    ]
    text = "Credit card: 4111-1111-1111-1111"
    fuse = fuse_cluster(spans, text=text, use_calibrated=True)
    assert fuse.resolved_type == EntityType.CREDIT_CARD
    assert fuse.confidence > 0.79
    print(f"  Multi-detector fused: {fuse.resolved_type.value} "
          f"confidence={fuse.confidence:.4f} (expected > 0.80) ✓")


def test_fuse_type_conflict():
    """Type conflicts should be resolved by majority vote."""
    spans = [
        CandidateSpan(
            entity_type=EntityType.CREDIT_CARD, start=0, end=19,
            confidence=0.90, detector="regex",
            value="4111-1111-1111-1111",
            raw={"checksum_valid": True},
        ),
        CandidateSpan(
            entity_type=EntityType.PERSON, start=0, end=19,
            confidence=0.60, detector="presidio",
            value="4111-1111-1111-1111",
            raw={},
        ),
    ]
    text = "CC: 4111-1111-1111-1111"
    fuse = fuse_cluster(spans, text=text, use_calibrated=True)
    # Regex has higher weight → CREDIT_CARD should win
    assert fuse.resolved_type == EntityType.CREDIT_CARD
    print(f"  Type conflict resolved: {fuse.resolved_type.value} "
          f"(majority: CREDIT_CARD > PERSON) ✓")


# ═══════════════════════════════════════════════════════════════════════════════
# ARBITRATOR END-TO-END TESTS
# ═══════════════════════════════════════════════════════════════════════════════


def test_arbitrator_end_to_end():
    """Full arbitrator pipeline should produce DetectedEntities."""
    arbitrator = Arbitrator()
    raw_detections = [
        {
            "entity_type": "EMAIL",
            "value": "alice@acme.com",
            "start": 5,
            "end": 19,
            "score": 0.92,
            "detector": "regex",
        },
        {
            "entity_type": "EMAIL",
            "value": "alice@acme.com",
            "start": 5,
            "end": 19,
            "score": 0.75,
            "detector": "presidio",
        },
        {
            "entity_type": "PHONE",
            "value": "+1-555-123-4567",
            "start": 30,
            "end": 45,
            "score": 0.85,
            "detector": "regex",
        },
    ]
    text = "Contact alice@acme.com or call +1-555-123-4567"

    import asyncio
    entities = asyncio.run(arbitrator.run(raw_detections, text=text))

    assert len(entities) == 2, f"Expected 2 entities, got {len(entities)}"
    assert entities[0].entity_type == EntityType.EMAIL
    assert entities[1].entity_type == EntityType.PHONE
    for e in entities:
        assert 0.0 <= e.confidence <= 1.0
        assert e.detector == "arbitrator"
        assert len(e.detector_votes) > 0
    print(f"  End-to-end: {len(entities)} entities ✓")
    for e in entities:
        print(f"    {e.entity_type.value}: {e.value[:30]} "
              f"confidence={e.confidence:.4f} "
              f"votes={len(e.detector_votes)}")


def test_arbitrator_empty():
    """Empty input should produce empty output."""
    arbitrator = Arbitrator()
    import asyncio
    entities = asyncio.run(arbitrator.run([], text=""))
    assert len(entities) == 0
    print("  Empty input: 0 entities ✓")


def test_without_calibration():
    """Config with use_calibrated_model=False should use weighted mean."""
    config = ArbitratorConfig(use_calibrated_model=False)
    arbitrator = Arbitrator(config)

    spans = [
        CandidateSpan(
            entity_type=EntityType.EMAIL, start=0, end=16,
            confidence=0.9, detector="regex",
            value="user@example.com",
        ),
    ]
    import asyncio
    entities = asyncio.run(arbitrator.run(
        [s.to_dict() for s in spans], text="Email: user@example.com"
    ))
    assert len(entities) == 1
    # Without calibration, score should be raw weighted mean
    print(f"  Uncalibrated: confidence={entities[0].confidence:.4f} "
          f"(should be 0.9) ✓")


# ═══════════════════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Calibrated Confidence Model — Test Suite")
    print("=" * 60)

    tests = [
        ("Logistic Regression — monotonic", test_calibrated_confidence_monotonic),
        ("Logistic Regression — range", test_calibrated_confidence_range),
        ("Logistic Regression — high confidence", test_calibrated_confidence_high_confidence),
        ("Logistic Regression — low confidence", test_calibrated_confidence_low_confidence),
        ("Features — CC with context", test_feature_extraction_cc_with_context),
        ("Features — no context", test_feature_extraction_no_context),
        ("Clustering — overlapping spans", test_cluster_overlapping_spans),
        ("Clustering — non-overlapping spans", test_cluster_non_overlapping_spans),
        ("Fusion — single detector", test_fuse_single_detector),
        ("Fusion — multi-detector agreement", test_fuse_multi_detector_agreement),
        ("Fusion — type conflict resolution", test_fuse_type_conflict),
        ("Arbitrator — end-to-end", test_arbitrator_end_to_end),
        ("Arbitrator — empty input", test_arbitrator_empty),
        ("Arbitrator — without calibration", test_without_calibration),
    ]

    passed = 0
    for name, func in tests:
        try:
            func()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(tests)} passed")
    print(f"{'=' * 60}")