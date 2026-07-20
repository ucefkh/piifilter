"""Data models for the arbitration layer.

These types define the contract between detectors and the Arbitrator:

- **CandidateSpan**: what a single detector reported (raw detection)
- **ClusterKey**: how overlapping spans are grouped (interval + dominant type)
- **EvidenceSource**: provenance meta for one detector's opinion
- **FusedEvidence**: merged result after clustering (all evidence + resolved type)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from piifilter.shared.models import DetectedEntity, EntityType


# ── EvidenceSource ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceSource:
    """Provenance record for one detector's opinion about a span.

    Every ``CandidateSpan`` that feeds into a cluster becomes one
    ``EvidenceSource`` in the final ``FusedEvidence.evidence`` list.
    """

    detector: str
    """Which detector reported this (e.g. ``"regex"``, ``"presidio"``, ``"gliner"``)."""

    entity_type: EntityType
    """The entity type this detector assigned."""

    confidence: float
    """Raw confidence score from this detector (0.0 – 1.0)."""

    start: int
    """Character offset where this detector's match starts (inclusive)."""

    end: int
    """Character offset where this detector's match ends (exclusive)."""

    raw: dict[str, Any] = field(default_factory=dict)
    """Optional extra metadata from the detector (analysis_explanation, etc.)."""


# ── CandidateSpan ────────────────────────────────────────────────────────────


@dataclass
class CandidateSpan:
    """A single detection from one detector before any fusion.

    This is the lowest-level unit in the arbitration pipeline. Every
    ``dict`` or ``DetectedEntity`` from a detector gets wrapped as a
    ``CandidateSpan`` before clustering.
    """

    entity_type: EntityType
    """The entity type this detector assigned."""

    start: int
    """Character offset where the match starts (inclusive)."""

    end: int
    """Character offset where the match ends (exclusive)."""

    confidence: float = 1.0
    """Raw confidence score from the detector (0.0 – 1.0)."""

    detector: str = "unknown"
    """Which detector reported this (e.g. ``"regex"``, ``"presidio"``)."""

    value: str = ""
    """The matched text span."""

    raw: dict[str, Any] = field(default_factory=dict)
    """Optional extra metadata from the detector."""

    # ── Factories ────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CandidateSpan:
        """Wrap a raw detection dict from a ``Detector.detect()`` call."""
        et = d.get("entity_type", d.get("type", "UNKNOWN"))
        if isinstance(et, str):
            et = EntityType(et)
        value = d.get("value", d.get("text", ""))
        return cls(
            entity_type=et,
            start=d.get("start", 0),
            end=d.get("end", 0),
            confidence=float(d.get("score", d.get("confidence", 1.0))),
            detector=str(d.get("detector", "unknown")),
            value=value if value else "",
            raw={k: v for k, v in d.items() if k not in ("entity_type", "start", "end", "score", "confidence", "value", "text", "detector", "type")},
        )

    @classmethod
    def from_detected_entity(cls, e: DetectedEntity) -> CandidateSpan:
        """Wrap a ``DetectedEntity`` instance (backward compat)."""
        return cls(
            entity_type=e.entity_type,
            start=e.start,
            end=e.end,
            confidence=e.confidence,
            detector=e.detector,
            value=e.value,
            raw={},
        )

    # ── Interval utilities ───────────────────────────────────────────

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: CandidateSpan, *, margin: int = 0) -> bool:
        """Do two spans overlap (allow *margin* chars of slack)?"""
        return self.start < other.end + margin and other.start < self.end + margin

    def contains(self, other: CandidateSpan) -> bool:
        """Does this span fully contain *other*?"""
        return self.start <= other.start and other.end <= self.end

    def union_span(self, other: CandidateSpan) -> tuple[int, int]:
        """Widest start/end across both spans."""
        return (min(self.start, other.start), max(self.end, other.end))

    # ── Ordering ─────────────────────────────────────────────────────

    def __lt__(self, other: CandidateSpan) -> bool:
        """Sort by start position, then by end position (shorter first)."""
        return (self.start, self.end) < (other.start, other.end)

    def key(self) -> tuple[int, int]:
        """Sort key as (start, end)."""
        return (self.start, self.end)


# ── ClusterKey ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class ClusterKey:
    """Unique identifier for a cluster of overlapping CandidateSpans.

    Defined by the majority-vote type and the outer span boundaries
    (widest start, widest end across all spans in the cluster).
    """

    resolved_type: EntityType
    """The entity type assigned by majority vote."""

    start: int
    """Widest start offset across all spans in the cluster."""

    end: int
    """Widest end offset across all spans in the cluster."""

    @classmethod
    def from_span_interval(
        cls, rounded_type: EntityType, start: int, end: int
    ) -> ClusterKey:
        return cls(resolved_type=rounded_type, start=start, end=end)


# ── FusedEvidence ────────────────────────────────────────────────────────────


@dataclass
class FusedEvidence:
    """Result of fusing a cluster's CandidateSpans into one coherent opinion.

    This is the intermediate representation between clustering and final
    ``DetectedEntity`` emission. It carries:

    * The *resolved* entity type (majority vote, with tie-breaking rules)
    * The aggregated start/end (outer span covering all candidates)
    * The fused confidence (weighted mean)
    * The full evidence chain for explainability
    """

    resolved_type: EntityType
    """Entity type after conflict resolution (majority vote + tie-breaker)."""

    start: int
    """Character offset — outer start (widest)."""

    end: int
    """Character offset — outer end (widest)."""

    confidence: float
    """Fused confidence score (0.0 – 1.0) across all evidence."""

    evidence: list[EvidenceSource] = field(default_factory=list)
    """All detector opinions that fed into this fusion result."""

    confidence_scores: list[float] = field(default_factory=list)
    """Raw confidence values for weighted-mean calculation (backing data)."""

    # ── Type distribution info ───────────────────────────────────────

    def type_vote_counts(self) -> dict[EntityType, int]:
        """Count how many evidence sources voted for each type."""
        counts: dict[EntityType, int] = {}
        for src in self.evidence:
            counts[src.entity_type] = counts.get(src.entity_type, 0) + 1
        return counts

    def type_confidence_mean(self, et: EntityType) -> float:
        """Mean confidence for a specific type across evidence sources."""
        scores = [s.confidence for s in self.evidence if s.entity_type == et]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def type_confidence_std(self, et: EntityType) -> float:
        """Standard deviation of confidence for a specific type."""
        scores = [s.confidence for s in self.evidence if s.entity_type == et]
        if len(scores) < 2:
            return 0.0
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return sqrt(variance)

    # ── Detector coverage ────────────────────────────────────────────

    def detector_count(self) -> int:
        """Number of *unique* detectors that contributed evidence."""
        return len({s.detector for s in self.evidence})

    def detectors_present(self) -> set[str]:
        """Set of detector names that contributed evidence."""
        return {s.detector for s in self.evidence}

    # ── Final emission ───────────────────────────────────────────────

    def to_detected_entity(self) -> DetectedEntity:
        """Emit a final ``DetectedEntity`` with fused evidence.

        The ``confidence`` on the entity reflects the weighted mean
        across all evidence sources. The ``detector`` field uses
        ``"arbitrator"`` to mark this as a fused result. The full
        evidence chain is preserved in ``detector_votes``.
        """
        return DetectedEntity(
            entity_type=self.resolved_type,
            value="",  # caller fills from original text
            start=self.start,
            end=self.end,
            confidence=self.confidence,
            detector="arbitrator",
            source_detector="arbitrator",
            detector_votes=[
                {
                    "detector": s.detector,
                    "entity_type": s.entity_type.value,
                    "confidence": s.confidence,
                    "start": s.start,
                    "end": s.end,
                }
                for s in self.evidence
            ],
        )