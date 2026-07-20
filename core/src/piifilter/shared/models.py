"""Shared data models for PIIFilter v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EntityType(str, Enum):
    """All 26 PII entity types PIIFilter detects and handles."""
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    CITY = "CITY"
    COUNTRY = "COUNTRY"
    COMPANY = "COMPANY"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    IBAN = "IBAN"
    CREDIT_CARD = "CREDIT_CARD"
    PASSPORT = "PASSPORT"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    JWT = "JWT"
    API_KEY = "API_KEY"
    SSH_KEY = "SSH_KEY"
    DATABASE_URL = "DATABASE_URL"
    PRIVATE_URL = "PRIVATE_URL"
    PROJECT_NAME = "PROJECT_NAME"
    CUSTOMER_NAME = "CUSTOMER_NAME"
    EMPLOYEE_NAME = "EMPLOYEE_NAME"
    GPS = "GPS"
    DOMAIN = "DOMAIN"
    IP_ADDRESS = "IP_ADDRESS"
    FILE_PATH = "FILE_PATH"
    DATE = "DATE"
    URL = "URL"


class ReplacementMode(str, Enum):
    MASK = "mask"
    SEMANTIC = "semantic"
    GENERALIZE = "generalize"
    POLICY = "policy"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DetectedEntity:
    """A single PII entity detected in the prompt.

    Contains full provenance — which detector found it, confidence score,
    and text position. Backward-compat property aliases (type, text, score)
    allow existing pipeline code to work unchanged.
    """
    entity_type: EntityType
    value: str
    start: int
    end: int
    confidence: float = 1.0
    detector: str = "unknown"          # which detector found it (regex, presidio, gliner)
    source_detector: str = ""          # alias kept for v1 compat
    detector_votes: list[dict] = field(default_factory=list)  # all detector opinions

    # ── Property aliases (backward-compat with sibling code) ──────
    @property
    def type(self) -> EntityType:
        return self.entity_type

    @type.setter
    def type(self, val: EntityType) -> None:
        self.entity_type = val

    @property
    def text(self) -> str:
        return self.value

    @text.setter
    def text(self, val: str) -> None:
        self.value = val

    @property
    def score(self) -> float:
        return self.confidence

    @score.setter
    def score(self, val: float) -> None:
        self.confidence = val

    @property
    def length(self) -> int:
        return self.end - self.start

    def __len__(self) -> int:
        return self.length


@dataclass
class RiskAssessment:
    """Risk evaluation with score, level, reason codes, and explainability."""
    score: float = 0.0
    level: RiskLevel = RiskLevel.LOW
    detected_count: int = 0
    critical_entities: list[str] = field(default_factory=list)
    recommendation: str = ""
    details: list[dict] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    def is_critical(self) -> bool:
        return self.level in (RiskLevel.CRITICAL, "critical", "CRITICAL")


@dataclass
class CandidateSpan:
    """A candidate match from a detector, with raw score and explainable features.

    Represents one PII detection before arbitration. Each detector emits
    CandidateSpan objects that the Arbitrator consumes and fuses together.
    The ``features`` dict provides explainability: why was this score assigned,
    what auxiliary signals (checksum, context keywords, format class) were found.

    Fields
    ------
    start, end : int
        Character offsets in the original (cleaned) text.
    text : str
        The matched substring.
    entity_type : EntityType
        The PII category (EMAIL, CREDIT_CARD, SSN, etc.).
    detector : str
        Which emitter produced this span (``regex``, ``presidio``, ``gliner``).
    raw_score : float
        Raw confidence score from the detector (0.0–1.0).  Not yet fused
        by the Arbitrator.
    features : dict[str, Any]
        Explainable feature dict.  Canonical keys (populated by the regex
        detector):

        * ``checksum_valid`` (bool) — Luhn check passed for credit cards,
          or area/group/serial validation passed for SSNs.  ``None`` when
          not applicable.
        * ``context_keywords`` (list[str]) — Surrounding context keywords
          that influenced detection (e.g. ``["ssn", "social security"]``).
          Empty when none found.
        * ``format_class`` (str) — Format variant detected (e.g.
          ``"4-4-4-4"``, ``"dotted"``, ``"keyword-prefixed"``,
          ``"masked"``, ``"bare-digit"``).
    """
    start: int
    end: int
    text: str
    entity_type: EntityType | str
    detector: str
    raw_score: float
    features: dict = field(default_factory=dict)

    @property
    def length(self) -> int:
        return self.end - self.start

    def to_dict(self) -> dict:
        """Serialize to the dict format expected by the telemetry / pipeline."""
        return {
            "text": self.text,
            "type": self.entity_type.value if isinstance(self.entity_type, Enum) else self.entity_type,
            "start": self.start,
            "end": self.end,
            "score": self.raw_score,
            "detector": self.detector,
            "features": self.features,
        }


@dataclass
class NormalizedText:
    """Holds a normalized view of text with offset mapping back to original bytes.

    The ``offset_map`` is a list parallel to the normalized text where each
    entry is either:
      - An integer index into the *original* text (1-to-1 mapping)
      - ``None`` (inserted character with no original counterpart)

    ``original`` stores the source text that this view was derived from.

    Use ``map_span_to_original(start, end)`` to map a span in the normalized
    text back to its original-coordinate span.
    """
    text: str
    offset_map: list[int | None] = field(default_factory=list)
    original: str = ""

    def map_span_to_original(self, start: int, end: int) -> tuple[int, int]:
        """Map a (start, end) span in this normalized text to coordinates
        in the original text.

        Returns ``(orig_start, orig_end)`` where both indices are clamped
        to valid positions in ``original``.  When the normalized span spans
        characters that have no original counterpart (inserted during
        normalization), the returned span still covers the right region
        because only *deletions* compress the offset map — inserted chars
        (``None`` entries) are skipped.
        """
        if not self.offset_map:
            return (start, end)
        # Walk forward from start to find the first non-None mapping
        o_start = start
        while o_start < len(self.offset_map) and self.offset_map[o_start] is None:
            o_start += 1
        if o_start >= len(self.offset_map):
            orig_start = len(self.original) - 1 if self.original else 0
        else:
            orig_start = self.offset_map[o_start]  # type: ignore[operator]

        # Walk backward from end to find the last non-None mapping
        o_end = min(end - 1, len(self.offset_map) - 1)
        while o_end >= 0 and self.offset_map[o_end] is None:
            o_end -= 1
        if o_end < 0:
            orig_end = 0
        else:
            val = self.offset_map[o_end]
            # The original character that maps to this position is at index val.
            # end is exclusive, so the span in the original is (o_start .. val+1).
            assert val is not None
            orig_end = val + 1

        # Clamp
        orig_start = max(0, min(orig_start, len(self.original)))
        orig_end = max(orig_start, min(orig_end, len(self.original)))
        return (orig_start, orig_end)


@dataclass
class Replacement:
    """A single replacement applied to the prompt."""
    original: str
    replacement: str
    entity_type: EntityType
    start: int = 0
    end: int = 0
    mode: ReplacementMode = ReplacementMode.SEMANTIC