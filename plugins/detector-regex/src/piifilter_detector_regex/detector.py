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
from piifilter.shared.deobfuscator import Deobfuscator

from . import patterns

# ── Context-window fallback classifier ──────────────────────────────────
# Trigger words that suggest a nearby number might be a CC, SSN, or
# financial account identifier — even if structural regex failed.
CTX_CC_SSN_TRIGGERS: set[str] = {
    "card", "credit", "cc", "cvv", "cvc",
    "exp", "expiry", "expiration",
    "ssn", "social", "security",
    "acct", "account", "routing", "aba", "pan",
    "number", "num",
}

# Compiled regex: match any trigger word (case-insensitive) followed by
# up to ~60 chars of filler, then a digit sequence (6–19 consecutive
# digits, or 4+4+4+4 / 3+2+4 patterns with ANY single separator).
# The trigger word must be followed by a non-word/non-hyphen boundary
# (colon, space, or end of input) to avoid matching "SSN-like" patterns.
# The bare-digit variant requires a word boundary before the digits and
# at least 6 digits — short numbers like "123" near words like "number"
# in non-PII contexts (e.g. "ticket number", "phone number") are excluded.
_CTX_CC_SSN_RE = re.compile(
    r"(?i)\b("
    + "|".join(re.escape(w) for w in sorted(CTX_CC_SSN_TRIGGERS, key=len, reverse=True))
    + r")\b(?!-).{0,60}?"
    r"(?P<digits>(?:\b\d{6,19}|(?:\d{4}[- .\u00A0•*#Xx*]{1}\d{4}[- .\u00A0•*#Xx*]{1}\d{4}[- .\u00A0•*#Xx*]{1}\d{2,4})|(?:\d{3}[- .\u00A0•*#Xx*]{1}\d{2}[- .\u00A0•*#Xx*]{1}\d{4})))",
    re.UNICODE,
)


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
        self._deobfuscator = Deobfuscator()
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

        Text is first run through the deobfuscation preprocessor
        (NFKC normalize, unwrap [at]/[dot], HTML entities, zero-width
        chars, fullwidth ASCII, unicode escapes) then regex patterns
        are applied against the cleaned text.

        Returns a list of dicts with keys: text, type, start, end, score, detector.
        """
        cleaned, _log = self._deobfuscator(text)
        entities = self._run_patterns(cleaned)
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

        Text is first run through the deobfuscation preprocessor
        (NFKC normalize, [at]/[dot], HTML entities, zero-width, etc.).

        Returns a list of ``DetectedEntity`` instances sorted by start position.
        Shortcut that bypasses the dict conversion of ``detect(text)``.
        """
        cleaned, _log = self._deobfuscator(session.prompt)
        return self._run_patterns(cleaned)

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
            # Use re.UNICODE — patterns use inline (?i) flags for case-insensitivity,
            # and (?-i:...) to selectively disable it. re.IGNORECASE would override
            # the (?-i:...) flag and break patterns that require case sensitivity.
            pattern = re.compile(raw_pattern, re.UNICODE)
            compiled.append((entity_type, pattern, score))
        return compiled

    @staticmethod
    def _luhn_valid(digits: str) -> bool:
        """Validate a digit string using the Luhn algorithm (ISO/IEC 7812).

        Returns True if the checksum passes. Requires at least 13 digits
        (the minimum length for a real credit card number).
        """
        nums = [int(d) for d in digits if d.isdigit()]
        if len(nums) < 13:
            return False
        # Double every second digit from the right (starting at the
        # second-to-last position, i.e. index len-2, then len-4, …)
        for i in range(len(nums) - 2, -1, -2):
            nums[i] *= 2
            if nums[i] > 9:
                nums[i] -= 9
        return sum(nums) % 10 == 0

    def _run_patterns(self, text: str) -> list[DetectedEntity]:
        """Run all compiled patterns against *text* with basic overlap dedup.

        CREDIT_CARD matches are validated with the Luhn algorithm: if the
        matched text contains 13+ digits that fail the checksum the match
        is discarded, eliminating false positives from random 16-digit
        numbers and IBAN trailing segments.
        """
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

                # Luhn validation for CREDIT_CARD: discard matches whose
                # digit content fails the checksum.
                if entity_type == EntityType.CREDIT_CARD:
                    digits = "".join(c for c in match.group() if c.isdigit())
                    if len(digits) >= 13 and not self._luhn_valid(digits):
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

        # ── Context-window fallback pass ──────────────────────────────
        # After all structural patterns have run, scan for digit sequences
        # that sit near trigger words (card, credit, ssn, etc.) but which
        # no pattern matched.  Assign low recall-biased confidence (0.55)
        # so the downstream score threshold can still accept them.
        cc_ssn_covered: set[tuple[int, int]] = {
            (e.start, e.end)
            for e in entities
            if e.entity_type in (EntityType.CREDIT_CARD, EntityType.SOCIAL_SECURITY)
        }
        for ctx_match in _CTX_CC_SSN_RE.finditer(text):
            ctx_end = ctx_match.start() + len(ctx_match.group())
            digits_raw = ctx_match.group("digits")
            if not digits_raw:
                continue

            dstart = ctx_match.start() + ctx_match.group().index(digits_raw)
            dend = dstart + len(digits_raw)

            # Skip if this span is already covered by a CC or SSN match
            if any(s <= dstart and dend <= e for s, e in cc_ssn_covered):
                continue

            # Decide type based on trigger word proximity
            trigger = ctx_match.group(1).lower()
            is_ssn_context = any(t in trigger for t in ("ssn", "social", "security"))
            is_cc_context = any(
                t in trigger for t in ("card", "credit", "cc", "cvv", "cvc", "exp", "expiry", "expiration", "pan")
            )

            if is_ssn_context:
                entity_type = EntityType.SOCIAL_SECURITY
            elif is_cc_context:
                entity_type = EntityType.CREDIT_CARD
            else:
                # Account/routing/aba/number without SSN/CC keyword —
                # default to SOCIAL_SECURITY since SSNs have fewer false
                # positives for account-like numbers
                entity_type = EntityType.SOCIAL_SECURITY

            entities.append(
                DetectedEntity(
                    entity_type=entity_type,
                    value=digits_raw,
                    start=dstart,
                    end=dend,
                    confidence=0.55,
                    detector="regex",
                )
            )
            cc_ssn_covered.add((dstart, dend))

        entities.sort(key=lambda e: e.start)
        return entities


def _resolve_entity_type(name: str) -> EntityType:
    """Resolve a pattern type name to a valid ``EntityType`` enum value.

    Some type names used in patterns (e.g. JWT, IBAN, GPS) are not
    present in the core ``EntityType`` enum, so they are mapped to
    the closest matching value or ``EntityType.PERSON``.
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
    # New entity types we added to PATTERN_DEFS that map directly:
    _DIRECT_MAP = {
        "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
        "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
        "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
        "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
        "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
        "DATE", "URL",
    }
    if name in _DIRECT_MAP:
        return EntityType(name)
    lookup = _LEGACY_MAP.get(name, name.lower())
    # If the lookup value isn't a valid EntityType, try the fallback
    try:
        return EntityType(lookup)
    except ValueError:
        fallback = _FALLBACK_MAP.get(lookup, "person")
        return EntityType(fallback)