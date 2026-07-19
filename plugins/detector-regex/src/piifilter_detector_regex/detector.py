"""RegexDetector — high-speed regex-based PII detector plugin.

Detects PII entities by running compiled regex patterns on session prompts.
Patterns are defined in the companion ``patterns.py`` module.
"""

from __future__ import annotations

import re
import time
from typing import Any, Pattern

from piifilter.interfaces.detector import Detector
from piifilter.session import Session
from piifilter.shared.models import DetectedEntity, EntityType
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter.telemetry import telemetry

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
        chars, fullwidth ASCII, unicode escapes) then inner-separator
        stripping collapses obfuscated numeric spans, then regex patterns
        are applied against the cleaned text.

        IMPORTANT: GPS patterns are run on the deobfuscated-but-not-stripped
        text because inner-separator stripping destroys decimal places in
        coordinate values (e.g. 40.7128 -> 407128), making GPS undetectable.
        """
        t0 = time.monotonic()
        cleaned, _log, text_for_gps = self._deobfuscator(text)
        # Run GPS patterns BEFORE inner-separator stripping (dots are essential
        # for GPS coordinate matching — stripping would destroy them).
        gps_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.GPS})
        # Now strip inner separators and run remaining patterns
        stripped = Deobfuscator._strip_inner_separators(cleaned)
        entities, cc_ssn_spans = self._run_patterns(stripped)
        # Structural recall pass: Luhn check on ALL 13-19 digit runs
        # and SSN validator on ALL exactly-9-digit runs not already matched.
        luhn_found = self._run_luhn_on_numeric_runs(stripped, cc_ssn_spans)
        entities.extend(luhn_found)
        ssn_found = self._validate_ssn_runs(stripped, cc_ssn_spans)
        entities.extend(ssn_found)
        # Merge GPS entities (from pre-strip text) with the rest (from stripped text)
        # GPS entities from pre-strip text use original positions in pre-strip text,
        # which matches the original unsplit position in the raw text after deobfuscation.
        entities.extend(gps_entities)
        entities.sort(key=lambda e: e.start)
        elapsed = time.monotonic() - t0

        # ── Telemetry hook ──────────────────────────────────────────
        result = [
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
        telemetry.record(elapsed=elapsed, detections=result, transforms=_log)
        return result

    # ── Session-based detection ──────────────────────────────────────

    async def detect_session(self, session: Session) -> list[DetectedEntity]:
        """Run compiled regex patterns on ``session.prompt``.

        Text is first run through the deobfuscation preprocessor
        (NFKC normalize, [at]/[dot], HTML entities, zero-width, etc.)
        then inner-separator stripping collapses obfuscated numeric spans.

        IMPORTANT: GPS patterns are run on pre-strip text (see detect() docs).
        """
        cleaned, _log, text_for_gps = self._deobfuscator(session.prompt)
        # GPS: run on pre-strip text so decimal places survive
        gps_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.GPS})
        stripped = Deobfuscator._strip_inner_separators(cleaned)
        entities, cc_ssn_spans = self._run_patterns(stripped)
        # Structural recall pass
        luhn_found = self._run_luhn_on_numeric_runs(stripped, cc_ssn_spans)
        entities.extend(luhn_found)
        ssn_found = self._validate_ssn_runs(stripped, cc_ssn_spans)
        entities.extend(ssn_found)
        entities.extend(gps_entities)
        entities.sort(key=lambda e: e.start)
        return entities

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

    @classmethod
    def _luhn_check(cls, digits: str) -> bool:
        """Standard Luhn algorithm. Returns True if check digit passes."""
        if not digits.isdigit() or len(digits) < 13 or len(digits) > 19:
            return False
        total = 0
        reverse = digits[::-1]
        for i, c in enumerate(reverse):
            n = ord(c) - 48
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    @staticmethod
    def _ssn_area_group_serial_valid(ssn_digits: str) -> bool:
        """Validate a 9-digit string using SSN area/group/serial rules.

        Validates that:
          - Area (first 3 digits): != '000', != '666', not in range '900'-'999'
          - Group (middle 2 digits): != '00'
          - Serial (last 4 digits): != '0000'

        Returns True if all checks pass.
        """
        if len(ssn_digits) != 9 or not ssn_digits.isdigit():
            return False
        area = ssn_digits[:3]
        group = ssn_digits[3:5]
        serial = ssn_digits[5:]
        return (
            area != "000"
            and area != "666"
            and not ("900" <= area <= "999")
            and group != "00"
            and serial != "0000"
        )

    def _run_patterns(self, text: str) -> tuple[list[DetectedEntity], set[tuple[int, int]]]:
        """Run all compiled patterns against *text* with basic overlap dedup.

        CREDIT_CARD matches are validated with the Luhn algorithm: if the
        matched text contains 13+ digits that fail the checksum the match
        is discarded, eliminating false positives from random 16-digit
        numbers and IBAN trailing segments.

        Returns
        -------
        (entities, cc_ssn_spans)
            entities — list of detected entities sorted by start position.
            cc_ssn_spans — set of (start, end) intervals for every CREDIT_CARD
            and SOCIAL_SECURITY match found by patterns (used by structural
            recall validators to avoid double-counting).
        """
        if not text:
            return [], set()

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
                    if len(digits) >= 13 and not self._luhn_check(digits):
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

        # Build set of (start, end) intervals for CC/SSN matches only —
        # used by structural validators to avoid double-counting.
        cc_ssn_spans: set[tuple[int, int]] = {
            (e.start, e.end)
            for e in entities
            if e.entity_type in (EntityType.CREDIT_CARD, EntityType.SOCIAL_SECURITY)
        }

        return entities, cc_ssn_spans

    def _run_patterns_for_type(
        self, text: str, entity_types: set[EntityType]
    ) -> tuple[list[DetectedEntity], set[tuple[int, int]]]:
        """Run only patterns matching *entity_types* against *text*.

        Used for types whose patterns must be run on the pre-strip text
        (before inner-separator stripping destroys key characters like dots).
        Currently used for GPS coordinates.

        Returns
        -------
        (entities, cc_ssn_spans)
        """
        if not text:
            return [], set()
        entities: list[DetectedEntity] = []
        seen_intervals: list[tuple[int, int]] = []

        for entity_type, pattern, score in self._patterns:
            if entity_type not in entity_types:
                continue
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                if start == end:
                    continue
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
        cc_ssn_spans: set[tuple[int, int]] = set()
        return entities, cc_ssn_spans

    def _run_luhn_on_numeric_runs(
        self, text: str, covered_spans: set[tuple[int, int]]
    ) -> list[DetectedEntity]:
        """Scan for all 13-19 consecutive digit runs not already covered by
        a pattern match and emit CREDIT_CARD at confidence 0.95 if Luhn passes.

        This is a structural recall safety net: after separator-stripping
        (done by the deobfuscator), any CC format variant reduces to a bare
        digit run that this method can catch. Only fires when the span was
        NOT already detected by a pattern match.
        """
        found: list[DetectedEntity] = []
        # Match 13-19 consecutive digits
        for m in re.finditer(r"\b\d{13,19}\b", text):
            start, end = m.start(), m.end()
            digits = m.group()

            # Skip if already covered by a pattern match
            if any(s <= start and end <= e for s, e in covered_spans):
                continue

            if self._luhn_check(digits):
                found.append(
                    DetectedEntity(
                        entity_type=EntityType.CREDIT_CARD,
                        value=digits,
                        start=start,
                        end=end,
                        confidence=0.95,
                        detector="regex",
                    )
                )
        return found

    @staticmethod
    def _validate_ssn_runs(
        text: str, covered_spans: set[tuple[int, int]]
    ) -> list[DetectedEntity]:
        """Scan for all exactly-9 consecutive digit runs not already covered
        by a pattern match and emit SOCIAL_SECURITY at confidence 0.95 if
        area/group/serial validation passes.

        Validation rules (from SSA):
          - Area (first 3 digits): not 000, not 666, not 900-999
          - Group (middle 2 digits): not 00
          - Serial (last 4 digits): not 0000
        """
        found: list[DetectedEntity] = []
        for m in re.finditer(r"(?<!\d)\d{9}(?!\d)", text):
            start, end = m.start(), m.end()
            digits = m.group()

            # Skip if already covered by a pattern match
            if any(s <= start and end <= e for s, e in covered_spans):
                continue

            area = int(digits[0:3])
            group = int(digits[3:5])
            serial = int(digits[5:9])

            if area == 0 or area == 666 or area >= 900:
                continue
            if group == 0:
                continue
            if serial == 0:
                continue

            found.append(
                DetectedEntity(
                    entity_type=EntityType.SOCIAL_SECURITY,
                    value=digits,
                    start=start,
                    end=end,
                    confidence=0.95,
                    detector="regex",
                )
            )
        return found


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