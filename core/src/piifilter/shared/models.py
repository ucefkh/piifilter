"""Shared data models for PIIFilter v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EntityType(str, Enum):
    """All 24 PII entity types PIIFilter detects and handles."""
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
class Replacement:
    """A single replacement applied to the prompt."""
    original: str
    replacement: str
    entity_type: EntityType
    start: int = 0
    end: int = 0
    mode: ReplacementMode = ReplacementMode.SEMANTIC