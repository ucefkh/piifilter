"""Presidio-based PII detector plugin.

Wraps Microsoft Presidio AnalyzerEngine for PII detection, mapping
presidio entity types to the system's EntityType enum. Falls back
gracefully if presidio-analyzer is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from piifilter.interfaces.detector import Detector
from piifilter.shared.models import EntityType

logger = logging.getLogger(__name__)

# ── Presidio-to-EntityType mapping ──────────────────────────────────────────

PRESIDIO_TYPE_MAP: dict[str, EntityType] = {
    "EMAIL_ADDRESS": EntityType.EMAIL,
    "PHONE_NUMBER": EntityType.PHONE,
    "US_SSN": EntityType.SSN,
    "US_DRIVER_LICENSE": EntityType.DRIVERS_LICENSE,
    "US_PASSPORT": EntityType.PASSPORT,
    "US_BANK_NUMBER": EntityType.BANK_ACCOUNT,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "IP_ADDRESS": EntityType.IP_ADDRESS,
    "PERSON": EntityType.NAME,
    "LOCATION": EntityType.ADDRESS,
    "DATE_TIME": EntityType.DATE_OF_BIRTH,
    "URL": EntityType.URL,
    "API_KEY": EntityType.API_KEY,
}

PRESIDIO_KNOWN_ENTITIES: set[str] = set(PRESIDIO_TYPE_MAP.keys())


def _presidio_to_entity_type(presidio_type: str) -> EntityType:
    """Map a Presidio entity type string to the system's EntityType.

    Returns ``EntityType.UNKNOWN`` for unmapped types so the pipeline
    never crashes on unrecognised presidio labels.
    """
    return PRESIDIO_TYPE_MAP.get(presidio_type, EntityType.UNKNOWN)


# ── PresidioDetector ────────────────────────────────────────────────────────


class PresidioDetector(Detector):
    """PII detector that wraps Microsoft Presidio AnalyzerEngine.

    Detection runs offloaded to a thread via ``asyncio.to_thread``
    because presidio-analyzer uses synchronous NLP pipelines internally.

    If presidio-analyzer is not installed the detector logs a warning
    and returns empty results on every ``detect()`` call.
    """

    # ── Class-level flag so we only log the import warning once ──────
    _presidio_available: bool = False
    _import_warning_logged: bool = False

    @property
    def name(self) -> str:
        return "presidio"

    # ── Lifecycle ───────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Attempt to import and create the Presidio AnalyzerEngine.

        If presidio-analyzer is missing, detection will return empty
        lists gracefully — the pipeline does not break.
        """
        if PresidioDetector._import_warning_logged:
            return

        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore[import-untyped]

            self._engine: Any = AnalyzerEngine()
            PresidioDetector._presidio_available = True
            logger.info(
                "PresidioDetector initialized (presidio-analyzer ready)"
            )
        except ImportError:
            self._engine = None
            PresidioDetector._presidio_available = False
            logger.warning(
                "presidio-analyzer is not installed. "
                "PresidioDetector will return empty results. "
                "Install with: pip install presidio-analyzer"
            )
        except Exception as exc:
            self._engine = None
            PresidioDetector._presidio_available = False
            logger.warning(
                "Presidio AnalyzerEngine failed to initialise: %s. "
                "Detection will return empty results.",
                exc,
            )
        finally:
            PresidioDetector._import_warning_logged = True

    async def shutdown(self) -> None:
        """Release presidio resources (if any)."""
        if self._engine is not None:
            logger.info("PresidioDetector shutting down")
            self._engine = None

    # ── Core detection ───────────────────────────────────────────────

    async def detect(
        self,
        text: str,
        *,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Detect PII entities in *text*.

        Detection is offloaded to a thread via ``asyncio.to_thread`` to
        avoid blocking the event loop on presidio's synchronous NLP.

        Parameters
        ----------
        text:
            The text to analyse.
        language:
            Language hint passed to Presidio (e.g. ``\"en\"``).
            Defaults to ``\"en\"`` if not provided.

        Returns
        -------
        List of detection dicts with keys:
            ``entity_type`` (str), ``start``, ``end``, ``score``,
            ``value``, ``detector``, ``analysis_explanation`` (optional).
        """
        if not PresidioDetector._presidio_available or self._engine is None:
            logger.debug("Presidio not available — returning empty results")
            return []

        lang = language or "en"

        try:
            results: list[Any] = await asyncio.to_thread(
                self._engine.analyze,
                text=text,
                language=lang,
            )

            detections: list[dict[str, Any]] = []
            for r in results:
                mapped = _presidio_to_entity_type(r.entity_type)
                detection: dict[str, Any] = {
                    "entity_type": mapped.value,
                    "start": r.start,
                    "end": r.end,
                    "score": float(r.score),
                    "value": text[r.start : r.end],
                    "detector": self.name,
                }
                # Attach explanation text if available (presidio >= 2.x)
                explanation = getattr(r, "analysis_explanation", None)
                if explanation is not None:
                    detection["analysis_explanation"] = explanation
                detections.append(detection)

            return detections

        except Exception as exc:
            logger.error(
                "Presidio analysis failed: %s", exc, exc_info=True
            )
            return []

    # ── Supported entities ───────────────────────────────────────────

    async def supported_entities(self) -> list[EntityType]:
        """Return the entity types this detector can recognise."""
        return list(set(PRESIDIO_TYPE_MAP.values()))

    # ── Debug helpers ────────────────────────────────────────────────

    def __repr__(self) -> str:
        ready = PresidioDetector._presidio_available
        return f"PresidioDetector(name={self.name!r}, ready={ready})"