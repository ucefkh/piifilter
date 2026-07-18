"""DetectionEngine — orchestrates multiple detectors and merges results."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from piifilter.config import FilterConfig
from piifilter.detection.presidio_detector import PresidioDetector
from piifilter.detection.regex_detector import RegexDetector
from piifilter.shared.models import DetectedEntity, EntityType

logger = logging.getLogger(__name__)


class DetectionEngine:
    """Orchestrates parallel PII detection across multiple backends.

    Currently runs:
        - ``RegexDetector``  — high-speed regex patterns
        - ``PresidioDetector`` — NER-based detection via presidio-analyzer

    Stub placeholder for a future ``GLiNERDetector``.
    """

    def __init__(self, config: FilterConfig) -> None:
        self.config = config
        self.regex_detector = RegexDetector()
        self.presidio_detector = PresidioDetector()
        # Future: self.gliner_detector = GLiNERDetector()  # (not yet implemented)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def detect(
        self,
        text: str,
        entity_filter: Optional[list[EntityType]] = None,
    ) -> list[DetectedEntity]:
        """Run all detectors, merge and deduplicate results.

        Parameters
        ----------
        text:
            Raw input text to scan.
        entity_filter:
            If provided, only return entities whose ``EntityType`` is in this list.

        Returns
        -------
        list[DetectedEntity]
            Sorted by start position, de-duplicated (prefer higher score for overlapping
            spans), and filtered by *entity_filter*.
        """
        if not text:
            return []

        # Phase 1 — run detectors in parallel ─────────────────────────
        regex_task = asyncio.to_thread(self.regex_detector.detect, text)
        presidio_task = self.presidio_detector.detect(text)

        regex_results, presidio_results = await asyncio.gather(
            regex_task, presidio_task, return_exceptions=True
        )

        # Handle errors per-detector so one failure doesn't kill everything
        if isinstance(regex_results, Exception):
            logger.warning("RegexDetector failed: %s", regex_results)
            regex_results = []
        if isinstance(presidio_results, Exception):
            logger.warning("PresidioDetector failed: %s", presidio_results)
            presidio_results = []

        # Phase 2 — merge & deduplicate ───────────────────────────────
        all_entities = self._deduplicate(
            regex_results + presidio_results  # type: ignore[operator]
        )

        # Phase 3 — filter ────────────────────────────────────────────
        if entity_filter is not None:
            filter_set = set(entity_filter)
            all_entities = [e for e in all_entities if e.type in filter_set]

        return all_entities

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    @staticmethod
    def _deduplicate(entities: list[DetectedEntity]) -> list[DetectedEntity]:
        """Remove overlapping entities, keeping the one with the higher score.

        Strategy:
            1. Sort by (start, -score) so higher-scored items come first for the
               same start position.
            2. Walk the list greedily: if the current entity does *not* overlap
               the last kept entity, keep it. If it *does* overlap, compare scores
               and keep the one with the higher score (preferring the already-kept
               one on a tie to remain stable).
        """
        if not entities:
            return []

        # Sort by start ↕, then by score ↕ (higher first)
        sorted_entities = sorted(entities, key=lambda e: (e.start, -e.score))

        deduped: list[DetectedEntity] = [sorted_entities[0]]
        for cand in sorted_entities[1:]:
            last = deduped[-1]
            if cand.start >= last.end:
                # No overlap — safe to append
                deduped.append(cand)
            else:
                # Overlap — keep the one with the higher score
                if cand.score > last.score:
                    deduped[-1] = cand
                # else keep the existing one (ties → stable)
        return deduped