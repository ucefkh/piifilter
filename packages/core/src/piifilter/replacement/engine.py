"""Replacement engine — replaces detected PII entities using configurable modes.

Four replacement modes:
- MASK:      Replace with entity type label, e.g. [PERSON]
- SEMANTIC:  Replace with realistic fake (alias), e.g. Susan → Janette
- GENERALIZE: Replace with category-level generalization, e.g. 42 Broadway → 'a downtown business district'
- POLICY:    Same as semantic but checks policy dict for overrides first
"""

from __future__ import annotations

from typing import Optional

from piifilter.config import FilterConfig
from piifilter.shared.models import DetectedEntity, EntityType, Replacement, ReplacementMode
from piifilter.shared.utils import generate_alias, mask_text


# Curated generalisation mapping for entity types.
_GENERALIZATION_MAP: dict[EntityType, list[str]] = {
    EntityType.ADDRESS: [
        "a downtown business district",
        "an urban commercial center",
        "a corporate office park",
    ],
    EntityType.CITY: [
        "a major metropolitan area",
        "a mid-size urban center",
        "a suburban community",
    ],
    EntityType.COUNTRY: [
        "a foreign jurisdiction",
        "a domestic market",
    ],
    EntityType.COMPANY: [
        "a technology company",
        "a financial institution",
        "a corporate entity",
    ],
    EntityType.PHONE: ["a telephone number"],
    EntityType.EMAIL: ["an email address"],
    EntityType.CREDIT_CARD: ["a payment method"],
    EntityType.BANK_ACCOUNT: ["a financial account"],
    EntityType.IBAN: ["an international bank account"],
    EntityType.PASSPORT: ["identification document"],
    EntityType.SOCIAL_SECURITY: ["government identifier"],
    EntityType.JWT: ["an authentication credential"],
    EntityType.API_KEY: ["an authentication credential"],
    EntityType.SSH_KEY: ["an authentication credential"],
    EntityType.DATABASE_URL: ["a database connection string"],
    EntityType.PRIVATE_URL: ["an internal resource"],
    EntityType.GPS: ["a geographic location"],
    EntityType.IP_ADDRESS: ["a network address"],
    EntityType.FILE_PATH: ["a file location"],
    EntityType.DOMAIN: ["a web domain"],
    EntityType.PERSON: ["an individual"],
    EntityType.CUSTOMER_NAME: ["a client organization"],
    EntityType.EMPLOYEE_NAME: ["a team member"],
    EntityType.PROJECT_NAME: ["a project"],
}


class ReplacementEngine:
    """Replaces detected PII entities in text using the configured mode.

    Processes entities in **reverse position order** (end-of-text to start-of-text)
    so that earlier string positions remain valid after each replacement.
    """

    def __init__(self, config: FilterConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def replace(
        self,
        text: str,
        entities: list[DetectedEntity],
        mode: ReplacementMode,
        policy: Optional[dict] = None,
    ) -> tuple[str, list[Replacement]]:
        """Replace detected entities in *text* using the given *mode*.

        Returns
        -------
        (filtered_text, replacements)
            *filtered_text* – the modified string with entities replaced.
            *replacements*  – metadata describing every change applied.
        """
        if not entities:
            return text, []

        # Sort entities in *descending* start position so we work right-to-left.
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)

        replacements: list[Replacement] = []
        buf = text

        for entity in sorted_entities:
            replacement_text = self._format(entity, mode, policy)
            # Replace the slice occupied by the entity.
            buf = buf[: entity.start] + replacement_text + buf[entity.end :]

            replacements.append(
                Replacement(
                    original=entity.text,
                    replacement=replacement_text,
                    entity_type=entity.type,
                    mode=mode,
                )
            )

        return buf, replacements

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format(self, entity: DetectedEntity, mode: ReplacementMode, policy: Optional[dict]) -> str:
        if mode == ReplacementMode.MASK:
            return self._format_mask(entity)
        elif mode == ReplacementMode.SEMANTIC:
            return self._format_semantic(entity)
        elif mode == ReplacementMode.GENERALIZE:
            return self._format_generalize(entity)
        elif mode == ReplacementMode.POLICY:
            return self._format_policy(entity, policy)
        # Fallback (should never reach here with valid modes).
        return self._format_semantic(entity)

    def _format_mask(self, entity: DetectedEntity) -> str:
        """Replace entity text with a masked label like ``[PERSON]``."""
        return mask_text(entity.text, entity.type.value)

    def _format_semantic(self, entity: DetectedEntity) -> str:
        """Replace entity text with a realistic fake via deterministic alias."""
        return generate_alias(entity.text, self.config.replacement.seed)

    def _format_generalize(self, entity: DetectedEntity) -> str:
        """Replace entity text with a category-level generalisation."""
        options = _GENERALIZATION_MAP.get(entity.type)
        if not options:
            # Unknown entity type — fall back to semantic.
            return self._format_semantic(entity)

        # Deterministic selection based on entity text hash.
        idx = abs(hash(entity.text)) % len(options)
        return options[idx]

    def _format_policy(self, entity: DetectedEntity, policy: Optional[dict]) -> str:
        """Apply policy overrides, falling back to semantic replacement."""
        if policy:
            # Policy dict can specify per-entity-type overrides or exact-text overrides.
            # Priority: exact text match > entity type override > semantic fallback.
            entity_type_key = entity.type.value

            if entity.text in policy:
                return str(policy[entity.text])

            if entity_type_key in policy:
                override = policy[entity_type_key]
                if isinstance(override, str):
                    return override
                if isinstance(override, list) and override:
                    idx = abs(hash(entity.text)) % len(override)
                    return str(override[idx])

        return self._format_semantic(entity)