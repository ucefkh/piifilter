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

        # ── Pre-strip patterns ─────────────────────────────────────────
        # These entity types MUST run on deobfuscated-but-NOT-stripped text
        # because _strip_inner_separators removes dots, dashes, slashes, and
        # other separators that are essential for pattern matching.
        #
        # GPS    — dots in coordinates (e.g. 40.7128) are destroyed by stripping
        # DATE   — "/" and "-" in dates (12/31/2025, 2024-01-15) are destroyed
        # IP_ADDRESS — dots in dotted-decimal IPs (192.168.1.100) are destroyed,
        #             causing ALL standard IPv4 addresses to be missed after
        #             stripping reduces them to bare digit runs. Without this fix,
        #             only the unreliable decimal-IP catch-all pattern (score 0.65)
        #             fires, producing false positives on SSN-like and date-like
        #             digit runs while missing real IPs entirely.
        gps_entities, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.GPS}
        )
        date_entities, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.DATE}
        )
        ip_entities, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.IP_ADDRESS}
        )

        # ── Now strip inner separators for structural patterns ──────────
        # After stripping, patterns like bare-digit CC, SSN, API keys, etc.
        # can match. IP patterns MUST NOT run here because stripping has
        # already destroyed dotted-decimal format.
        stripped = Deobfuscator._strip_inner_separators(cleaned)
        entities, cc_ssn_spans = self._run_patterns(stripped)
        # Structural recall pass: Luhn check on ALL 13-19 digit runs
        # and SSN validator on ALL exactly-9-digit runs not already matched.
        luhn_found = self._run_luhn_on_numeric_runs(stripped, cc_ssn_spans)
        entities.extend(luhn_found)
        ssn_found = self._validate_ssn_runs(stripped, cc_ssn_spans)
        entities.extend(ssn_found)
        # Merge pre-strip entities (GPS + DATE + IP) with the rest (from stripped text)
        entities.extend(gps_entities)
        entities.extend(date_entities)
        entities.extend(ip_entities)
        entities.sort(key=lambda e: e.start)

        # ── Cross-type dedup: low-confidence PHONE entities that overlap with ──
        # IPs, GPS, or DATE entities on the ORIGINAL text. After stripping,
        # bare-digit phone patterns (e.g. 10-digit continuous) can match the
        # digit-run remains of a dotted IP (e.g. 47.94.124.103 → 4794124103).
        # We detect this by checking if the phone's pure-digit value matches
        # the pure-digit value of a pre-strip IP/GPS/DATE entity.
        entities = self._filter_phone_overlap(entities, ip_entities, gps_entities, date_entities)

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
        # Pre-strip patterns: GPS, DATE, IP — these need dots/slashes/dashes
        # to survive, which _strip_inner_separators destroys.
        gps_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.GPS})
        date_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.DATE})
        ip_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.IP_ADDRESS})
        stripped = Deobfuscator._strip_inner_separators(cleaned)
        entities, cc_ssn_spans = self._run_patterns(stripped)
        # Structural recall pass
        luhn_found = self._run_luhn_on_numeric_runs(stripped, cc_ssn_spans)
        entities.extend(luhn_found)
        ssn_found = self._validate_ssn_runs(stripped, cc_ssn_spans)
        entities.extend(ssn_found)
        entities.extend(gps_entities)
        entities.extend(date_entities)
        entities.extend(ip_entities)
        entities.sort(key=lambda e: e.start)

        # ── Cross-type PHONE dedup (same as detect() — see notes there) ──
        entities = self._filter_phone_overlap(entities, ip_entities, gps_entities, date_entities)

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

    @staticmethod
    def _filter_phone_overlap(
        entities: list[DetectedEntity],
        ip_entities: list[DetectedEntity],
        gps_entities: list[DetectedEntity],
        date_entities: list[DetectedEntity],
    ) -> list[DetectedEntity]:
        """Remove low-confidence PHONE entities whose digit content matches
        an IP, GPS, or DATE entity from pre-strip detection.

        After inner-separator stripping, bare-digit phone patterns can
        match the residue of dotted IPs (e.g. 47.94.124.103 → 4794124103).
        Since pre-strip entities use original-text coordinates and stripped
        entities use stripped-text coordinates, we match by digit content
        rather than position.
        """
        if not entities:
            return entities

        # Build lookup: pure-digit string → set of entity types it came from
        pre_strip_digits: dict[str, set[str]] = {}
        for src_label, src_list in [
            ("ip", ip_entities),
            ("gps", gps_entities),
            ("date", date_entities),
        ]:
            for se in src_list:
                sd = "".join(c for c in se.value if c.isdigit())
                if sd:
                    pre_strip_digits.setdefault(sd, set()).add(src_label)

        filtered: list[DetectedEntity] = []
        for e in entities:
            if e.entity_type == EntityType.PHONE and e.confidence <= 0.75:
                ed = "".join(c for c in e.value if c.isdigit())
                if ed:
                    # Check if the phone digit content either matches or
                    # contains a pre-strip entity's digit content (e.g. IP
                    # "192.168.1.1" + suffix "/16" → phone "1921681116"
                    # contains IP digits "19216811").
                    skip = False
                    for psd in pre_strip_digits:
                        if psd in ed or ed in psd:
                            skip = True
                            break
                    if skip:
                        # This phone match overlaps with (or is contained
                        # by) a pre-strip IP/GPS/date entity — suppress it.
                        continue
            filtered.append(e)
        return filtered

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

                # Numeric validation for decimal IP: ensure value is in valid
                # 32-bit unsigned integer range (16777216 to 4294967295).
                # This prevents 8-digit dates like "12312025" (Dec 31, 2025)
                # from being misclassified as decimal IP addresses.
                # Additional anti-FP heuristics suppress SSN and phone numbers
                # that happen to decode to valid IP octets.
                if entity_type == EntityType.IP_ADDRESS and score < 0.80:
                    # Low-confidence IP patterns (decimal IP) need numeric validation
                    ip_text = match.group()
                    digits_only = "".join(c for c in ip_text if c.isdigit())
                    if len(digits_only) >= 7:
                        try:
                            ip_int = int(digits_only)
                            if ip_int < 16777216 or ip_int > 4294967295:
                                continue
                        except ValueError:
                            continue

                    # ── Anti-SSN heuristic: exclude 9-digit numbers that pass
                    # SSN area/group/serial validation — they are SSNs, not IPs.
                    # Also exclude numbers with SSN context keywords regardless
                    # of area validity (catches demo SSNs like 911-68-3710).
                    if len(digits_only) == 9:
                        # Check SSN context keywords in surrounding text
                        context_before = text[max(0, start - 50):start].lower()
                        context_after = text[end:min(len(text), end + 30)].lower()
                        ssn_keywords = ("ssn", "social security", "tax id", "ss#")
                        if any(kw in context_before for kw in ssn_keywords):
                            continue
                        area, group, serial = digits_only[:3], digits_only[3:5], digits_only[5:]
                        if (area != "000" and area != "666"
                                and not ("900" <= area <= "999")
                                and group != "00" and serial != "0000"):
                            continue

                    # ── Anti-phone / anti-bank heuristic: exclude 10-digit numbers
                    # that are preceded by phone or bank-account context keywords,
                    # or that start with '1' without IP context (likely NANP phone).
                    if len(digits_only) == 10:
                        context_before = text[max(0, start - 50):start].lower()
                        phone_keywords = (
                            "phone", "tel", "mobile", "cell", "call",
                            "contact", "dial", "number"
                        )
                        bank_keywords = (
                            "bank", "account", "acct", "a/c"
                        )
                        if any(kw in context_before for kw in phone_keywords):
                            continue
                        if any(kw in context_before for kw in bank_keywords):
                            continue
                        # NANP phone numbers: 10-digit numbers starting with '1'
                        # are virtually always NANP phones (1-XXX-XXX-XXXX).
                        # However, some genuine decimal IPs (e.g. 168430090)
                        # are 9 digits, so this only affects 10-digit '1xxxx...'
                        # numbers. Keep if preceded by IP-related context.
                        ip_context = text[max(0, start - 30):start].lower()
                        if digits_only.startswith("1") and "ip" not in ip_context:
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
        Currently used for GPS, DATE, and IP_ADDRESS.

        For IP_ADDRESS on pre-strip text, context guards prevent the
        dotted-decimal pattern from firing on non-IP dotted numerics:
        version numbers, dates, SSNs, phone numbers, and other numeric
        sequences that happen to fall in valid IP octet ranges.

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

                # ── IP_ADDRESS context guards (pre-strip text) ──────────────
                # Dotted-decimal IP patterns can falsely match version numbers,
                # dates with dot separators, phone fragments, and SSN fragments.
                # These guards run ONLY on pre-strip IP detection where the
                # actual dotted format survives.
                if entity_type == EntityType.IP_ADDRESS:
                    ip_text = match.group()

                    # --- Anti-date guard: skip if first two octets are valid
                    # month/day (1-12/1-31), indicating a date like "12.31.2025"
                    # or "3.14.1592" rather than an IP address.
                    dots = ip_text.count(".")
                    if dots >= 2:
                        # Extract the first two dot-separated groups
                        groups = ip_text.split(".")
                        if len(groups) >= 2:
                            try:
                                first = int(groups[0])
                                second = int(groups[1])
                                # Month (1-12) + valid day (1-31) = very likely a date
                                if 1 <= first <= 12 and 1 <= second <= 31:
                                    # Only skip for standard dotted-decimal (4 groups),
                                    # not for hex/octal/space-separated formats
                                    if dots == 3:
                                        continue
                            except ValueError:
                                pass

                    # --- Semver / version number guard: skip if dotted groups
                    # look like a semantic version (e.g. 1.2.3, 2.0.1, 10.0.0)
                    # where ALL groups are small (< 256) and the first group
                    # is a very small number typical of versions (< 10).
                    if dots == 2:
                        groups = ip_text.split(".")
                        if len(groups) == 3:
                            try:
                                g = [int(x) for x in groups]
                                # Common version pattern: major.minor.patch
                                # where major < 10 and all groups < 256
                                if g[0] <= 9 and all(0 <= x <= 255 for x in g):
                                    continue
                                # Also skip when first two octets are < 10 and
                                # third < 256 — likely version or measurement
                                if g[0] <= 5 and g[1] <= 99 and g[2] <= 255:
                                    continue
                            except ValueError:
                                pass

                    # --- Context keyword guard: check surrounding text for
                    # non-IP context keywords that suggest this is SSN, phone,
                    # or date data rather than an IP address.
                    if dots == 3:
                        context_before = text[max(0, start - 60):start].lower()
                        context_after = text[end:min(len(text), end + 30)].lower()
                        # Combine all non-IP keywords. Only skip if context
                        # suggests non-IP data WITHOUT "ip" also in context
                        # (e.g. "ip address: 192.168.1.1" should NOT be skipped).
                        non_ip_keywords = (
                            # SSN keywords
                            "ssn", "social security", "tax id", "ss#",
                            # Date keywords
                            "date", "dob", "born", "expir", "updated",
                            "valid until", "issued", "created on",
                            # Phone keywords
                            "phone", "tel", "mobile", "cell", "call",
                            "contact", "dial", "number",
                            # Bank keywords
                            "bank", "account", "acct", "a/c",
                            # Version/measurement keywords
                            "version", "ver.", "v.", "release",
                            "build", "rev", "revision",
                        )
                        any_non_ip = any(kw in context_before for kw in non_ip_keywords)
                        any_non_ip_after = any(kw in context_after for kw in non_ip_keywords)
                        has_ip_context = "ip" in context_before
                        if any_non_ip and not has_ip_context:
                            continue
                        # Also skip if the text AFTER the match suggests date/version
                        # (catches cases where context is before the IP pattern but
                        # the surrounding text is not keyword-prefixed)
                        if any_non_ip_after and not has_ip_context:
                            continue

                    # --- Decimal IP catch-all guard (score < 0.80):
                    # Only emit low-confidence IP from pre-strip text if it
                    # passes SSN, phone, and date validation (same as _run_patterns).
                    if score < 0.80:
                        # --- Numeric range validation ---
                        digits_only = "".join(c for c in ip_text if c.isdigit())
                        if len(digits_only) >= 7:
                            try:
                                ip_int = int(digits_only)
                                if ip_int < 16777216 or ip_int > 4294967295:
                                    continue
                            except ValueError:
                                continue

                        # --- Anti-SSN heuristic ---
                        if len(digits_only) == 9:
                            context_before = text[max(0, start - 50):start].lower()
                            context_after = text[end:min(len(text), end + 30)].lower()
                            ssn_keywords = ("ssn", "social security", "tax id", "ss#")
                            if any(kw in context_before for kw in ssn_keywords):
                                continue
                            area, group, serial = digits_only[:3], digits_only[3:5], digits_only[5:]
                            if (area != "000" and area != "666"
                                    and not ("900" <= area <= "999")
                                    and group != "00" and serial != "0000"):
                                continue

                        # --- Anti-phone / anti-bank heuristic ---
                        if len(digits_only) == 10:
                            context_before = text[max(0, start - 50):start].lower()
                            phone_keywords = (
                                "phone", "tel", "mobile", "cell", "call",
                                "contact", "dial", "number"
                            )
                            bank_keywords = ("bank", "account", "acct", "a/c")
                            if any(kw in context_before for kw in phone_keywords):
                                continue
                            if any(kw in context_before for kw in bank_keywords):
                                continue
                            ip_context = text[max(0, start - 30):start].lower()
                            if digits_only.startswith("1") and "ip" not in ip_context:
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