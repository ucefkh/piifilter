"""GeneralizationStrategy — replaces PII entity text with general category labels."""

from __future__ import annotations

from logging import getLogger
from typing import Any

from piifilter.interfaces.strategy import ReplacementStrategy
from piifilter.shared.models import DetectedEntity, EntityType, Replacement, ReplacementMode

logger = getLogger(__name__)


# Map of entity types to their generalised / human-readable description.
# When an entity type is not found in this map the fallback string
# ``"a piece of sensitive information"`` is used.
_GENERALIZATION_MAP: dict[str, str] = {
    EntityType.EMAIL.value: "an email address",
    EntityType.PHONE.value: "a phone number",
    EntityType.SOCIAL_SECURITY.value: "a social security number",
    EntityType.CREDIT_CARD.value: "a payment method",
    EntityType.IP_ADDRESS.value: "an IP address",
    EntityType.PERSON.value: "an individual",
    EntityType.ADDRESS.value: "a physical address",
}


def generalize(entity_type: str | EntityType) -> str:
    """Return the generalised description for a given entity type.

    Args:
        entity_type: The entity type (string or :class:`EntityType` enum).

    Returns:
        A human-friendly generalised label such as ``"an individual"``
        or ``"a payment method"``.
    """
    key = entity_type.value if isinstance(entity_type, EntityType) else entity_type
    return _GENERALIZATION_MAP.get(key, "a piece of sensitive information")


class GeneralizationStrategy(ReplacementStrategy):
    """Replacement strategy that replaces PII with a general category label.

    Instead of exposing the raw entity type name (e.g. ``[CREDIT_CARD]``)
    or a fake alias, this strategy replaces values with human-friendly
    descriptions such as ``"a payment method"`` or ``"an individual"``.
    This provides a natural-language read that is informative enough for
    most downstream consumers while avoiding both the original data and
    the specific entity type name.

    Entities are processed in reverse position order (end-of-string first)
    so that earlier replacements do not shift the character offsets of
    later replacements.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._name = kwargs.pop("name", "generalize")

    # ── ReplacementStrategy interface ──────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    async def apply(self, text: str, detections: list[dict]) -> str:
        """Apply generalization replacement to detected PII in *text*.

        Args:
            text: The original prompt text.
            detections: A list of detection dicts, each expected to have
                at least ``start``, ``end``, and ``type`` (or ``entity_type``) keys.

        Returns:
            The text with all detected spans replaced by generalised labels.
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
            if isinstance(et, EntityType):
                label = generalize(et)
            else:
                label = generalize(str(et))
            result = result[:start] + label + result[end:]
        return result

    async def replace(
        self,
        session: Any,
        entities: list[DetectedEntity],
    ) -> tuple[str, list[Replacement]]:
        """Replace detected entities in the session prompt with generalised labels.

        Args:
            session: The pipeline ``Session`` object (provides ``session.prompt``).
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
            label = generalize(entity.type)
            prompt = prompt[: entity.start] + label + prompt[entity.end :]

            replacements.append(
                Replacement(
                    original=entity.value,
                    replacement=label,
                    entity_type=entity.type,
                    start=entity.start,
                    end=entity.start + len(label),
                    mode=ReplacementMode.STATIC,
                    reversible=False,
                    metadata={
                        "entity_type": entity.type.value,
                        "strategy": "generalize",
                    },
                )
            )

        logger.debug(
            "GeneralizationStrategy applied %d replacement(s)", len(replacements)
        )
        return prompt, replacements

    async def initialize(self) -> None:
        logger.info("GeneralizationStrategy initialized")

    async def shutdown(self) -> None:
        logger.info("GeneralizationStrategy shut down")