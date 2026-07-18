"""Risk scoring engine — evaluates prompt risk based on detected entities."""

from __future__ import annotations

from piifilter.config import FilterConfig
from piifilter.shared.models import (
    DetectedEntity,
    EntityType,
    RiskAssessment,
    RiskLevel,
)

# Points awarded per entity type category.
_CRITICAL_POINTS = 25
_HIGH_POINTS = 15
_MEDIUM_POINTS = 10
_LOW_POINTS = 5

# Duplicate penalty: reduce by 30% after the first occurrence.
_DUPLICATE_PENALTY = 0.30

# Entity types that are considered critical.
_CRITICAL_TYPES: frozenset[EntityType] = frozenset({
    EntityType.API_KEY,
    EntityType.JWT,
    EntityType.SSH_KEY,
    EntityType.DATABASE_URL,
    EntityType.SOCIAL_SECURITY,
    EntityType.CREDIT_CARD,
    EntityType.PASSPORT,
    EntityType.IBAN,
})

# Entity types considered high-risk.
_HIGH_TYPES: frozenset[EntityType] = frozenset({
    EntityType.BANK_ACCOUNT,
    EntityType.PRIVATE_URL,
    EntityType.GPS,
})

# Entity types considered medium-risk.
_MEDIUM_TYPES: frozenset[EntityType] = frozenset({
    EntityType.EMAIL,
    EntityType.PHONE,
    EntityType.ADDRESS,
    EntityType.FILE_PATH,
    EntityType.IP_ADDRESS,
})

# Lower-risk entity types.
_LOW_TYPES: frozenset[EntityType] = frozenset({
    EntityType.PERSON,
    EntityType.CITY,
    EntityType.COUNTRY,
    EntityType.COMPANY,
    EntityType.DOMAIN,
    EntityType.CUSTOMER_NAME,
    EntityType.EMPLOYEE_NAME,
    EntityType.PROJECT_NAME,
})

# Mapping from entity type to its base point value.
_TYPE_POINTS: dict[EntityType, int] = {}
for _t in _CRITICAL_TYPES:
    _TYPE_POINTS[_t] = _CRITICAL_POINTS
for _t in _HIGH_TYPES:
    _TYPE_POINTS[_t] = _HIGH_POINTS
for _t in _MEDIUM_TYPES:
    _TYPE_POINTS[_t] = _MEDIUM_POINTS
for _t in _LOW_TYPES:
    _TYPE_POINTS[_t] = _LOW_POINTS

# Threshold string → RiskLevel mapping.
_THRESHOLD_MAP: dict[str, RiskLevel] = {
    "low": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}

# Recommendations per risk level.
_RECOMMENDATIONS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "Proceed — minimal sensitive data detected",
    RiskLevel.MEDIUM: "Review — consider masking sensitive fields",
    RiskLevel.HIGH: "Review required — sensitive information detected",
    RiskLevel.CRITICAL: "Block prompt — critical credentials detected",
}


def _determine_level(score: float) -> RiskLevel:
    """Map a numeric score to a RiskLevel."""
    if score <= 25:
        return RiskLevel.LOW
    elif score <= 50:
        return RiskLevel.MEDIUM
    elif score <= 75:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def _resolve_threshold(config: FilterConfig) -> RiskLevel:
    """Map the string threshold from config to a RiskLevel."""
    return _THRESHOLD_MAP.get(config.risk.threshold.lower(), RiskLevel.MEDIUM)


class RiskEngine:
    """Risk assessment engine that scores prompts 0–100."""

    def __init__(self, config: FilterConfig) -> None:
        self._threshold = _resolve_threshold(config)

    async def assess(
        self,
        text: str,
        entities: list[DetectedEntity],
    ) -> RiskAssessment:
        """Score a prompt based on detected entities.

        Parameters
        ----------
        text : str
            The original prompt text (used for context; points are based on
            entities only).
        entities : list[DetectedEntity]
            Entities detected in the prompt.

        Returns
        -------
        RiskAssessment
            A fully populated risk assessment.
        """
        score = 0.0
        details: list[dict] = []
        critical_entities_set: set[EntityType] = set()

        # Track how many times we've seen each entity text so far.
        seen_counts: dict[str, int] = {}

        for entity in entities:
            entity_type = entity.type
            base_points = _TYPE_POINTS.get(entity_type, 0)

            # Apply duplicate penalty: first occurrence → full points,
            # subsequent occurrences → reduced by 30%.
            text = entity.text
            seen_counts[text] = seen_counts.get(text, 0) + 1
            if seen_counts[text] > 1:
                base_points = int(base_points * (1 - _DUPLICATE_PENALTY))

            score += base_points

            details.append({
                "text": entity.text,
                "type": entity_type.value,
                "points": base_points,
            })

            if entity_type in _CRITICAL_TYPES:
                critical_entities_set.add(entity_type)

        # Cap at 100.
        score = min(score, 100.0)

        level = _determine_level(score)
        recommendation = _RECOMMENDATIONS[level]

        return RiskAssessment(
            score=score,
            level=level,
            detected_count=len(entities),
            critical_entities=sorted(critical_entities_set, key=lambda e: e.value),
            recommendation=recommendation,
            details=details,
        )

    def _level_exceeds_threshold(self, level: RiskLevel) -> bool:
        """Return True if the assessed level exceeds the configured threshold."""
        severity_order = [
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        try:
            return severity_order.index(level) > severity_order.index(self._threshold)
        except ValueError:
            return False
