"""MaskStrategy — replaces PII entity text with [ENTITY_TYPE] labels."""

from __future__ import annotations

from logging import getLogger
from typing import Any

from piifilter.interfaces.strategy import ReplacementStrategy
from piifilter.shared.models import DetectedEntity, EntityType, Replacement, ReplacementMode
from piifilter.shared.utils import mask_text

logger = getLogger(__name__)


class MaskStrategy(ReplacementStrategy):
    """Replacement strategy that masks PII with an [ENTITY_TYPE] label.

    Each detected entity is replaced by a bracketed label derived from its
    entity type (e.g. ``[PERSON]``, ``[CREDIT_CARD]``, ``[EMAIL]``),
    making the category of the redacted information visible without
    disclosing the actual value.

    Entities are processed in reverse position order (end-of-string first)
    so that earlier replacements do not shift the character offsets of
    later replacements.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._name = kwargs.pop("name", "mask")

    # ── ReplacementStrategy interface ──────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    async def apply(self, text: str, detections: list[dict]) -> str:
        """Apply mask replacement to detected PII in *text*.

        Args:
            text: The original prompt text.
            detections: A list of detection dicts, each expected to have
                at least ``start``, ``end``, and ``type`` (or ``entity_type``) keys.

        Returns:
            The text with all detected spans replaced by mask labels.
        """
        reversed_detections = sorted(
            detections,
            key=lambda d: d.get("end", d.get("start", 0)),
            reverse=True,
        )
        result = text
        for d in reversed_detections:
            start = d["start"]
            end = d.get("end", start)
            et = d.get("entity_type", d.get("type", "unknown"))
            label = mask_text(result[start:end], entity_type=et if isinstance(et, str) else et.value)
            result = result[:start] + label + result[end:]
        return result

    async def replace(
        self,
        session: Any,
        entities: list[DetectedEntity],
    ) -> tuple[str, list[Replacement]]:
        """Replace detected entities in the session prompt with mask labels.

        Args:
            session: The pipeline ``Session`` object (used for ``session.prompt``
                and optionally ``session.config.replacement.seed``).
            entities: List of ``DetectedEntity`` instances to replace.

        Returns:
            A tuple of ``(filtered_text, replacements)`` where *replacements*
            is a list of ``Replacement`` dataclass instances recording every
            substitution.
        """
        prompt = session.prompt
        replacements: list[Replacement] = []

        # Process in reverse position order so offsets remain valid
        sorted_entities = sorted(entities, key=lambda e: e.end, reverse=True)

        for entity in sorted_entities:
            label = mask_text(entity.value, entity_type=entity.type.value)
            prompt = prompt[: entity.start] + label + prompt[entity.end :]

            replacements.append(
                Replacement(
                    original=entity.value,
                    replacement=label,
                    entity_type=entity.type,
                    start=entity.start,
                    end=entity.start + len(label),
                    mode=ReplacementMode.MASK,
                    reversible=True,
                    metadata={"entity_type": entity.type.value},
                )
            )

        logger.debug(
            "MaskStrategy applied %d replacement(s)", len(replacements)
        )
        return prompt, replacements

    async def initialize(self) -> None:
        logger.info("MaskStrategy initialized")

    async def shutdown(self) -> None:
        logger.info("MaskStrategy shut down")