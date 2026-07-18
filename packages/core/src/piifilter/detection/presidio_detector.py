"""Presidio-based NER detector (stub with fallback)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from piifilter.shared.models import DetectedEntity, EntityType

logger = logging.getLogger(__name__)

# Mapping from presidio entity labels → PIIFilter EntityType
PRESIDIO_MAP: dict[str, EntityType] = {
    "PERSON": EntityType.PERSON,
    "EMAIL": EntityType.EMAIL,
    "PHONE": EntityType.PHONE,
    "ADDRESS": EntityType.ADDRESS,
    "CITY": EntityType.CITY,
    "COUNTRY": EntityType.COUNTRY,
    "LOCATION": EntityType.ADDRESS,
    "COMPANY": EntityType.COMPANY,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "IP_ADDRESS": EntityType.IP_ADDRESS,
    "DATE_TIME": None,  # explicitly skipped
}


class PresidioDetector:
    """Detects PII entities via presidio-analyzer (NER-based).

    Falls back gracefully when presidio is not installed.
    """

    def __init__(self) -> None:
        self._engine: Optional[object] = None
        self._available = False
        self._init_engine()

    # ------------------------------------------------------------------
    # Initialization (graceful fallback)
    # ------------------------------------------------------------------
    def _init_engine(self) -> None:
        """Attempt to initialise the presidio-analyzer engine."""
        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore[import-untyped]

            self._engine = AnalyzerEngine()
            self._available = True
            logger.info("PresidioAnalyzer initialised successfully")
        except ImportError:
            self._available = False
            logger.warning(
                "presidio-analyzer not installed — PresidioDetector will return empty results. "
                "Install with: pip install presidio-analyzer"
            )
        except Exception as exc:
            self._available = False
            logger.warning("Failed to initialise PresidioAnalyzer: %s", exc)

    # ------------------------------------------------------------------
    # Detection (async, CPU-bound call offloaded to thread)
    # ------------------------------------------------------------------
    async def detect(self, text: str) -> list[DetectedEntity]:
        """Run presidio-analyzer on *text* and map results to PIIFilter entities.

        Offloads the CPU-bound presidio call to a thread via ``asyncio.to_thread``.
        """
        if not text or not self._available or self._engine is None:
            return []

        try:
            # presidio_analyzer is CPU-bound — run in thread to avoid blocking the event loop
            results = await asyncio.to_thread(self._engine.analyze, text=text, language="en")
        except Exception as exc:
            logger.warning("Presidio analysis failed: %s", exc)
            return []

        entities: list[DetectedEntity] = []
        for result in results:
            presidio_type = result.entity_type
            mapped = PRESIDIO_MAP.get(presidio_type)

            # Skip unmapped types (e.g. DATE_TIME we deliberately skip)
            if mapped is None:
                continue

            confidence = getattr(result, "score", 0.0)
            # Clamp score to [0.0, 1.0] and tag source
            score = max(0.0, min(1.0, confidence))

            entities.append(
                DetectedEntity(
                    text=text[result.start : result.end],
                    type=mapped,
                    start=result.start,
                    end=result.end,
                    score=score,
                    source_detector="presidio",
                )
            )

        entities.sort(key=lambda e: e.start)
        return entities