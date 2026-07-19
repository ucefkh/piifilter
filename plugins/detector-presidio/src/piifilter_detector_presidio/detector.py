"""Presidio-based PII detector plugin.

Wraps Microsoft Presidio AnalyzerEngine for PII detection, mapping
presidio entity types to the system's EntityType enum. Falls back
gracefully if presidio-analyzer is not installed.

Key decisions for false-positive control:
  - Only high-confidence entities (score >= 0.7) are returned.
  - Only presidio entity types with a high-precision mapping are kept;
    all others are dropped rather than defaulting to PERSON (which
    caused 0.14 precision on the benchmark).
  - DATE_TIME is dropped entirely — it was mapped to PERSON before,
    destroying PERSON precision.
  - URL is inspected: only ``private/internal`` URLs (hostnames without
    dots, or loopback/local addresses) map to PRIVATE_URL. All other
    URLs are dropped to avoid conflicting with Regex DOMAIN detection.
  - LOCATION and ADDRESS are mapped but filtered by the score threshold.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from piifilter.interfaces.detector import Detector
from piifilter.shared.models import EntityType

logger = logging.getLogger(__name__)

# ── Presidio-to-EntityType mapping ──────────────────────────────────────────
#
# Only map entities where presidio has demonstrated high precision.
# Dropped entirely (not listed here):
#   - DATE_TIME     → was mapped to PERSON → destroyed PERSON precision
#   - NUMBER / AGE  → not in the 24 entity types
#   - LOCATION      → mapped to ADDRESS but generates massive false positives (>30 FP)
#                     due to the 0.7 score floor being too permissive for NER noise
#   - DEFAULT       → not mapped

PRESIDIO_TYPE_MAP: dict[str, EntityType] = {
    # High-precision financial / identity entities
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "US_SSN": EntityType.SOCIAL_SECURITY,
    "US_PASSPORT": EntityType.PASSPORT,
    "US_DRIVER_LICENSE": EntityType.PASSPORT,
    "US_BANK_NUMBER": EntityType.BANK_ACCOUNT,
    # Contact info
    "EMAIL_ADDRESS": EntityType.EMAIL,
    "PHONE_NUMBER": EntityType.PHONE,
    # Network identifiers
    "IP_ADDRESS": EntityType.IP_ADDRESS,
    # Credentials
    "API_KEY": EntityType.API_KEY,
    # Person — re-enabled with high confidence threshold.
    # Regex PERSON has precision=1.0 but recall=0.718 on the held-out set.
    # Presidio NER catches full names regex misses (e.g. "Alice Johnson")
    # but generates false positives on common words at low confidence.
    # A higher confidence floor (0.85 vs 0.75 for other entities) prunes
    # those FPs while retaining most true-positive NER detections.
    "PERSON": EntityType.PERSON,
}

PRESIDIO_KNOWN_ENTITIES: set[str] = set(PRESIDIO_TYPE_MAP.keys())

# Minimum confidence score for presidio results to be included.
# This aggressively prunes the many low-confidence false positives
# that presidio's NER produces for generic text.
_MIN_SCORE: float = 0.75
# Higher confidence threshold for NER-based PERSON detection.
# Presidio's NER fires on common nouns and sentence fragments at low confidence;
# requiring >= 0.85 excludes most false positives while keeping real names.
_PERSON_MIN_SCORE: float = 0.85


_PRIVATE_URL_PREFIXES = (
    "https://localhost",
    "http://localhost",
    "https://127.0.0.1",
    "http://127.0.0.1",
    "https://10.",
    "http://10.",
    "https://172.16.",
    "http://172.16.",
    "https://192.168.",
    "http://192.168.",
    "https://[::1]",
    "http://[::1]",
)
"""Prefixes that distinguish private/internal URLs from public ones."""


def _is_private_url(url: str) -> bool:
    """Return True if *url* looks like a private / internal URL."""
    lower = url.lower().strip()
    if lower.startswith(_PRIVATE_URL_PREFIXES):
        return True
    # Hostname without dots (e.g. http://my-internal-service:8080/path)
    # could be an internal hostname — treat as private.
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(lower)
        hostname = parsed.hostname
        if hostname and "." not in hostname:
            return True
    except Exception:
        pass
    return False


def _presidio_to_entity_type(
    presidio_type: str,
    score: float,
    text: str | None = None,
) -> EntityType | None:
    """Map a Presidio entity to the system's EntityType (or None to drop).

    Parameters
    ----------
    presidio_type:
        The entity label returned by presidio (e.g. "PERSON", "URL").
    score:
        Presidio's confidence score for this detection.
    text:
        The original text span that was detected. Used for URL inspection.

    Returns
    -------
    The mapped ``EntityType``, or ``None`` if the entity should be
    dropped entirely (low confidence, unmappable, or known false-positive
    category).
    """
    # Hard score floor — drop everything below the threshold.
    # PERSON uses a higher threshold to prune NER false positives.
    threshold = _PERSON_MIN_SCORE if presidio_type == "PERSON" else _MIN_SCORE
    if score < threshold:
        return None

    # Special handling: URL → PRIVATE_URL only for private URLs.
    # Public URLs are dropped to avoid false-positive conflicts with
    # the regex-based DOMAIN detector.
    if presidio_type == "URL":
        if text is not None and _is_private_url(text):
            return EntityType.PRIVATE_URL
        return None

    # Standard mapping lookup. Unknown presidio types are dropped
    # rather than defaulting to PERSON (which tanked precision).
    return PRESIDIO_TYPE_MAP.get(presidio_type, None)


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
            Language hint passed to Presidio (e.g. ``\\"en\\"``).
            Defaults to ``\\"en\\"`` if not provided.

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
                span_text = text[r.start : r.end]
                mapped = _presidio_to_entity_type(
                    r.entity_type,
                    float(r.score),
                    text=span_text,
                )
                if mapped is None:
                    # Dropped — low score, unmappable, or known
                    # false-positive category.
                    continue

                detection: dict[str, Any] = {
                    "entity_type": mapped.value,
                    "start": r.start,
                    "end": r.end,
                    "score": float(r.score),
                    "value": span_text,
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
            """Return the entity types this detector can recognise.
            Include PRIVATE_URL even though it's not in PRESIDIO_TYPE_MAP
            (it's handled specially in _presidio_to_entity_type for URL).
            """
            types: set[EntityType] = set(PRESIDIO_TYPE_MAP.values())
            if EntityType.PRIVATE_URL not in types:
                types.add(EntityType.PRIVATE_URL)
            return list(types)
    # ── Debug helpers ────────────────────────────────────────────────

    def __repr__(self) -> str:
        ready = PresidioDetector._presidio_available
        return f"PresidioDetector(name={self.name!r}, ready={ready})"