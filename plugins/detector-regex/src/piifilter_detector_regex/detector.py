"""RegexDetector — high-speed regex-based PII detector plugin.

Detects PII entities by running compiled regex patterns on session prompts.
Patterns are defined in the companion ``patterns.py`` module.
"""

from __future__ import annotations

import re
from typing import Any, Pattern

from piifilter.interfaces.detector import Detector
from piifilter.session import Session
from piifilter.shared.models import DetectedEntity, EntityType

from . import patterns


class RegexDetector(Detector):
    """High-speed regex-based PII detector.

    Compiles all regex patterns from ``patterns.PATTERN_DEFS`` at init
    time and runs them against the session prompt or raw text on every
    ``detect()`` call.

    Scores are assigned per-pattern (0.75–0.95) based on specificity:
      - 0.95: cryptographic keys, tokens, database URLs, private keys
      - 0.90: most identifier patterns (email, IP, SSN, JWT, API keys)
      - 0.85: fuzzy/lower-specificity patterns (phone, domain, IBAN)
      - 0.80–0.75: broad patterns (passport digits, bank accounts)
    """

    def __init__(self) -> None:
        self._patterns: list[tuple[EntityType, Pattern[str], float]] = self._compile()
        self._name = "regex"
        self._version = "2.0.0"

    # ── Detector interface ───────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    async def initialize(self) -> None:
        """No-op: regex patterns are loaded at init time."""
        return

    async def shutdown(self) -> None:
        """No-op: nothing to release."""
        return

    async def detect(self, text: str, *, language: str | None = None) -> list[dict[str, Any]]:
        """Detect PII entities in *text*.

        Implements the core ``Detector`` interface method.
        Returns a list of dicts with keys: text, type, start, end, score, detector.
        """
        entities = self._run_patterns(text)
        return [
            {
                "text": e.value,
                "type": e.entity_type.value,
                "start": e.start,
                "end": e.end,
                "score": e.score,
                "detector": "regex",
            }
            for e in entities
        ]

    # ── Session-based detection ──────────────────────────────────────

    async def detect_session(self, session: Session) -> list[DetectedEntity]:
        """Run compiled regex patterns on ``session.prompt``.

        Returns a list of ``DetectedEntity`` instances sorted by start position.
        Shortcut that bypasses the dict conversion of ``detect(text)``.
        """
        return self._run_patterns(session.prompt)

    # ── Entity listing ──────────────────────────────────────────────

    async def supported_entities(self) -> list[EntityType]:
        """Return the entity types this detector can recognise."""
        seen: set[EntityType] = set()
        result: list[EntityType] = []
        for entity_type, _pattern, _score in self._patterns:
            if entity_type not in seen:
                seen.add(entity_type)
                result.append(entity_type)
        return result

    # ── Internal ─────────────────────────────────────────────────────

    def _compile(self) -> list[tuple[EntityType, Pattern[str], float]]:
        """Compile static pattern definitions into (EntityType, Pattern, score) tuples."""
        compiled: list[tuple[EntityType, Pattern[str], float]] = []
        for type_name, raw_pattern, score in patterns.PATTERN_DEFS:
            entity_type = _resolve_entity_type(type_name)
            pattern = re.compile(raw_pattern, re.IGNORECASE)
            compiled.append((entity_type, pattern, score))
        return compiled

    def _run_patterns(self, text: str) -> list[DetectedEntity]:
        """Run all compiled patterns against *text* with basic overlap dedup."""
        if not text:
            return []

        entities: list[DetectedEntity] = []
        seen_intervals: list[tuple[int, int]] = []

        for entity_type, pattern, score in self._patterns:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()

                # Skip zero-length matches
                if start == end:
                    continue

                # Skip if fully contained in an already-found match of the same type
                if any(s <= start and end <= e for s, e in seen_intervals):
                    continue

                entities.append(
                    DetectedEntity(
                        entity_type=entity_type,
                        value=match.group(),
                        start=start,
                        end=end,
                        confidence=score,
                        detector="regex",
                    )
                )
                seen_intervals.append((start, end))

        entities.sort(key=lambda e: e.start)
        return entities


def _resolve_entity_type(name: str) -> EntityType:
    """Resolve a pattern type name to a valid ``EntityType`` enum value.

    Some type names used in patterns (e.g. JWT, IBAN, GPS) are not
    present in the core ``EntityType`` enum, so they are mapped to
    the closest matching value or ``EntityType.UNKNOWN``.
    """
    _LEGACY_MAP: dict[str, str] = {
        "SOCIAL_SECURITY": "ssn",
    }
    # The core EntityType enum does not include all pattern type names.
    # Map non-core types to the closest available value.
    _FALLBACK_MAP: dict[str, str] = {
        "jwt": "token",
        "domain": "url",
        "database_url": "url",
        "private_url": "url",
        "file_path": "url",
        "ssh_key": "api_key",
        "iban": "bank_account",
        "gps": "unknown",
    }
    lookup = _LEGACY_MAP.get(name, name.lower())
    # If the lookup value isn't a valid EntityType, try the fallback
    try:
        return EntityType(lookup)
    except ValueError:
        fallback = _FALLBACK_MAP.get(lookup, "unknown")
        return EntityType(fallback)