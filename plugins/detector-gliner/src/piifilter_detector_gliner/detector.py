"""GLiNER-based PII detector — stub with graceful ImportError fallback.

GLiNER is a zero-shot NER model that can detect arbitrary entity types
from labels provided at inference time.  This stub provides the full
``Detector`` interface; it logs a warning and returns empty results
when ``gliner`` is not installed.

Because GLiNER models are downloaded on first use, the stub keeps a
placeholder for model-path configuration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from piifilter.interfaces.detector import Detector
from piifilter.shared.models import EntityType

logger = logging.getLogger(__name__)

# ── GLiNER-EntityType mapping (default labels) ──────────────────────────────

GLINER_LABEL_MAP: dict[str, EntityType] = {
    "person": EntityType.PERSON,
    "email": EntityType.EMAIL,
    "phone number": EntityType.PHONE,
    "address": EntityType.ADDRESS,
    "date of birth": EntityType.PERSON,
    "credit card": EntityType.CREDIT_CARD,
    "ssn": EntityType.SOCIAL_SECURITY,
    "passport number": EntityType.PASSPORT,
    "drivers license": EntityType.PASSPORT,
    "bank account": EntityType.BANK_ACCOUNT,
    "ip address": EntityType.IP_ADDRESS,
    "url": EntityType.PRIVATE_URL,
    "api key": EntityType.API_KEY,
    "license plate": EntityType.COMPANY,
    "medical record": EntityType.PERSON,
    "token": EntityType.JWT,
    "password": EntityType.API_KEY,
}

GLINER_KNOWN_LABELS: list[str] = list(GLINER_LABEL_MAP.keys())


def _gliner_label_to_entity_type(label: str) -> EntityType:
    """Map a GLiNER label string to the system's EntityType.

    Returns ``EntityType.PERSON`` for unmapped labels.
    """
    return GLINER_LABEL_MAP.get(label.lower(), EntityType.PERSON)


# ── GLiNERDetector ──────────────────────────────────────────────────────────


class GLiNERDetector(Detector):
    """PII detector wrapping a GLiNER zero-shot NER model.

    If ``gliner`` is not installed the detector logs a warning and
    returns empty results on every ``detect()`` call.

    .. note::

        This is a *stub* implementation.  The actual GLiNER model
        initialisation and inference code should be added when the
        dependency is available.
    """

    # ── Class-level flag so we only warn once ────────────────────────
    _gliner_available: bool = False
    _import_warning_logged: bool = False

    def __init__(self, model_name: str = "urchade/gliner_large-v2.5") -> None:
        self._model_name = model_name
        self._model: Any = None
        self._labels: list[str] = GLINER_KNOWN_LABELS

    @property
    def name(self) -> str:
        return "gliner"

    # ── Lifecycle ───────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Attempt to import and create the GLiNER model.

        On success the model is loaded and ready for inference.
        On failure (import error, OOM, etc.) the detector falls back
        to returning empty results.
        """
        if GLiNERDetector._import_warning_logged:
            return

        try:
            from gliner import GLiNER  # type: ignore[import-untyped]

            # Model loading is potentially slow — offload to a thread
            self._model = await asyncio.to_thread(
                GLiNER.from_pretrained, self._model_name
            )
            GLiNERDetector._gliner_available = True
            logger.info(
                "GLiNERDetector initialized with model %s",
                self._model_name,
            )
        except ImportError:
            self._model = None
            GLiNERDetector._gliner_available = False
            logger.warning(
                "gliner is not installed. "
                "GLiNERDetector will return empty results. "
                "Install with: pip install gliner"
            )
        except Exception as exc:
            self._model = None
            GLiNERDetector._gliner_available = False
            logger.warning(
                "GLiNER model '%s' failed to initialise: %s. "
                "Detection will return empty results.",
                self._model_name,
                exc,
            )
        finally:
            GLiNERDetector._import_warning_logged = True

    async def shutdown(self) -> None:
        """Release model resources."""
        if self._model is not None:
            logger.info("GLiNERDetector shutting down")
            self._model = None

    # ── Core detection ───────────────────────────────────────────────

    async def detect(
        self,
        text: str,
        *,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Detect PII entities in *text* using the GLiNER zero-shot model.

        Inference is offloaded to a thread via ``asyncio.to_thread``
        because GLiNER runs synchronously.

        Parameters
        ----------
        text:
            The text to analyse.
        language:
            Ignored for GLiNER (model is language-agnostic).  Present
            for interface compatibility.

        Returns
        -------
        List of detection dicts with keys:
            ``entity_type`` (str), ``start``, ``end``, ``score``,
            ``value``, ``detector``.
        """
        if not GLiNERDetector._gliner_available or self._model is None:
            logger.debug("GLiNER not available — returning empty results")
            return []

        try:
            # GLiNER's predict returns labels but not character spans
            # by default; we need the span variant.
            results: list[dict[str, Any]] = await asyncio.to_thread(
                self._model.predict_entities, text, self._labels
            )

            detections: list[dict[str, Any]] = []
            for r in results:
                mapped = _gliner_label_to_entity_type(r["label"])
                start = r.get("start", 0)
                end = r.get("end", len(text))
                detections.append(
                    {
                        "entity_type": mapped.value,
                        "start": start,
                        "end": end,
                        "score": float(r.get("score", 1.0)),
                        "value": text[start:end],
                        "detector": self.name,
                    }
                )

            return detections

        except Exception as exc:
            logger.error(
                "GLiNER inference failed: %s", exc, exc_info=True
            )
            return []

    # ── Supported entities ───────────────────────────────────────────

    async def supported_entities(self) -> list[EntityType]:
        """Return the entity types this detector can recognise."""
        return list(set(GLINER_LABEL_MAP.values()))

    # ── Debug helpers ────────────────────────────────────────────────

    def __repr__(self) -> str:
        ready = GLiNERDetector._gliner_available
        return (
            f"GLiNERDetector(name={self.name!r}, "
            f"model={self._model_name!r}, ready={ready})"
        )