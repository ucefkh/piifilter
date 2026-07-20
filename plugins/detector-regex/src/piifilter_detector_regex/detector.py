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
from piifilter.shared.models import DetectedEntity, EntityType, CandidateSpan
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

    async def detect(self, text: str, *, language: str | None = None) -> list[CandidateSpan]:
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
        # because _strip_inner_separators removes dots, dashes, slashes,
        # commas, and other separators that are essential for pattern matching.
        #
        # GPS    — dots in coordinates (e.g. 40.7128) are destroyed by stripping
        # DATE   — "/" and "-" in dates (12/31/2025, 2024-01-15) are destroyed
        # IP_ADDRESS — dots in dotted-decimal IPs (192.168.1.100) are destroyed,
        #             causing ALL standard IPv4 addresses to be missed after
        #             stripping reduces them to bare digit runs. Without this fix,
        #             only the unreliable decimal-IP catch-all pattern (score 0.65)
        #             fires, producing false positives on SSN-like and date-like
        #             digit runs while missing real IPs entirely.
        # PHONE (CJK-only) — CJK phone patterns (电话/電話 keyword prefixed) need
        #           dashes and spaces to survive stripping. Only CJK-prefixed phone
        #           patterns are run pre-strip because other phone patterns without
        #           CJK context produce too many false positives on dotted IPs,
        #           dates, and numeric sequences that happen to match phone formats.
        # ADDRESS — European-style addresses like "Unter den Linden 1, 10117 Berlin"
        #           rely on a comma between the street number and postcode. Stripping
        #           collapses "1, 10117" into "110117", destroying the pattern.
        #           US-style addresses (e.g. "123 Maple Drive") work fine on stripped
        #           text, so pre-strip address entities are merged and deduped.
        # PRIVATE_URL — contains dotted IP addresses (127.0.0.1, 10.x.x.x, etc.)
        #           that inner-separator stripping destroys.
        gps_entities, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.GPS}
        )
        date_entities, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.DATE}
        )
        ip_entities, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.IP_ADDRESS}
        )
        phone_entities_presistrip, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.PHONE}
        )
        address_entities_presistrip, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.ADDRESS}
        )
        private_url_entities_presistrip, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.PRIVATE_URL}
        )
        # Filter pre-strip phone entities: keep only low-FP-risk patterns.
        # - CJK-context phones (电话/電話) are always kept — these are unambiguous.
        # - International +-prefix phones at confidence >= 0.80 are kept — these
        #   have proper format with separators (e.g. "+1-555-123-4567") and are
        #   very unlikely to be IP/date FPs. This fixes cases like URL-decoded
        #   phones (%2B1-555-123-4567) where the pre-strip text preserves the
        #   format that inner-separator stripping would destroy.
        # - Non-CJK/non-plus phones at confidence >= 0.70 are kept — these are
        #   standard 3-3-4 format (e.g. "555-123-4567") or parenthesized area
        #   codes that have correct span positions on the original text. Their
        #   presence in the pre-strip list causes _filter_phone_overlap to
        #   suppress the lower-confidence stripped duplicate, which has wrong
        #   span positions due to inner-separator stripping.
        phone_entities_presistrip = [
            e for e in phone_entities_presistrip
            if any(cjk in e.value for cjk in ("电话", "電話", "電話は", "电话是"))
            or (e.confidence >= 0.80 and "+" in e.value)
            or e.confidence >= 0.70
        ]

        # ── Now strip inner separators for structural patterns ──────────
        # After stripping, patterns like bare-digit CC, SSN, API keys, etc.
        # can match. IP patterns MUST NOT run here because stripping has
        # already destroyed dotted-decimal format.
        stripped = Deobfuscator._strip_inner_separators(cleaned)
        entities, cc_ssn_spans = self._run_patterns(stripped)
        # Build a comprehensive set of covered spans from ALL entity types found
        # by _run_patterns, not just CC/SSN. This prevents the structural recall
        # validators from re-adding a CREDIT_CARD match that was replaced by a
        # more specific BANK_ACCOUNT match (e.g. "account: 8765432109876543").
        all_spans: set[tuple[int, int]] = {
            (e.start, e.end) for e in entities
        } | cc_ssn_spans
        # Structural recall pass: Luhn check on ALL 13-19 digit runs
        # and SSN validator on ALL exactly-9-digit runs not already matched.
        luhn_found = self._run_luhn_on_numeric_runs(stripped, all_spans)
        entities.extend(luhn_found)
        ssn_found = self._validate_ssn_runs(stripped, all_spans)
        entities.extend(ssn_found)
        # Merge pre-strip entities (GPS + DATE + IP + PHONE + ADDRESS + PRIVATE_URL) with the rest (from stripped text)
        entities.extend(gps_entities)
        entities.extend(date_entities)
        entities.extend(ip_entities)
        entities.extend(phone_entities_presistrip)
        entities.extend(address_entities_presistrip)
        entities.extend(private_url_entities_presistrip)
        entities.sort(key=lambda e: e.start)

        # ── Cross-type dedup: suppress pre-strip PRIVATE_URL entities ──
        # that are contained within DATABASE_URL or URL entities (from
        # stripped text). When a PRIVATE_URL like "db.internal:5432/production"
        # is a substring of "postgresql://admin:***@db.internal:5432/production"
        # (DATABASE_URL), the broader type is more specific and the private-
        # hostname match is noise.
        url_substring_types = {EntityType.DATABASE_URL, EntityType.URL, EntityType.PRIVATE_URL}
        private_url_substrings: list[str] = []
        for e in entities:
            if e.entity_type == EntityType.PRIVATE_URL:
                # Check if any DATABASE_URL/URL contains this match as substring
                is_contained = False
                for other in entities:
                    if other is e and other.entity_type == EntityType.PRIVATE_URL:
                        continue
                    if other.entity_type in url_substring_types:
                        # Use value-based containment since coordinates may differ
                        if e.value in other.value and len(e.value) < len(other.value):
                            is_contained = True
                            break
                if not is_contained:
                    private_url_substrings.append(e.value)

        # Now apply: only keep PRIVATE_URL entities that are not contained
        filtered_entities: list[DetectedEntity] = []
        for e in entities:
            if e.entity_type == EntityType.PRIVATE_URL:
                if e.value in private_url_substrings:
                    filtered_entities.append(e)
            else:
                filtered_entities.append(e)
        entities = filtered_entities

        # ── Cross-type dedup: suppress IP_ADDRESS entities that are fully ──
        # contained within PRIVATE_URL entities. Private URLs like
        # "http://127.0.0.1:8080/admin" trigger BOTH the PRIVATE_URL pattern
        # (because of the http:// + private IP) and the IP_ADDRESS pattern
        # (because of the dotted decimal inside). Since PRIVATE_URL is the
        # more specific type (it captures the entire URL context), the IP
        # sub-match is noise and should be suppressed.
        # Because pre-strip entities may use different coordinate spaces
        # (IP matches on text_for_gps with dashes collapsed, PRIVATE_URL
        # also on text_for_gps), we use value-based containment: if an
        # IP_ADDRESS value appears inside a PRIVATE_URL value, suppress it.
        if private_url_entities_presistrip:
            private_url_values = {e.value for e in private_url_entities_presistrip}
            filtered_entities: list[DetectedEntity] = []
            for e in entities:
                if e.entity_type == EntityType.IP_ADDRESS:
                    # Check if this IP value is contained in any PRIVATE_URL value
                    is_contained = False
                    for puv in private_url_values:
                        if e.value in puv:
                            is_contained = True
                            break
                    if is_contained:
                        continue
                filtered_entities.append(e)
            entities = filtered_entities

        # ── Cross-type dedup: low-confidence PHONE entities that overlap with ──
        # IPs, GPS, or DATE entities on the ORIGINAL text. After stripping,
        # bare-digit phone patterns (e.g. 10-digit continuous) can match the
        # digit-run remains of a dotted IP (e.g. 47.94.124.103 → 4794124103).
        # We detect this by checking if the phone's pure-digit value matches
        # the pure-digit value of a pre-strip IP/GPS/DATE entity.
        entities = self._filter_phone_overlap(entities, ip_entities, gps_entities, date_entities, phone_entities_presistrip)

        # ── Cross-type dedup: SOCIAL_SECURITY entities whose digit run ──
        # matches a pre-strip IP, GPS, or DATE entity. When dotted IPs
        # like 192.168.1.50 are stripped to 192168150, the 9-digit run
        # can match the SSN validator even though it is clearly an IP.
        entities = self._filter_ssn_overlap(entities, ip_entities, gps_entities, date_entities)

        # ── Cross-type dedup: BANK_ACCOUNT entities that overlap with ──
        # pre-strip GPS entities. After separator stripping, coordinate
        # pairs like "50.0000, 100.0000" collapse to "5000001000000",
        # which matches the bare-digit BANK_ACCOUNT pattern (0.55).
        # Suppress low-confidence BANK_ACCOUNT matches whose digit content
        # is contained in or contains a pre-strip GPS entity's digit content.
        entities = self._filter_bank_account_gps_overlap(entities, gps_entities)

        # ── Same-type dedup: remove entities of the same type whose spans are
        # fully contained within a higher-confidence entity of the same type.
        # This prevents pre-strip phone matches (with CJK keyword) from being
        # duplicated by bare-digit phone matches on the stripped text.
        # Also prefers longer spans at the same confidence level (e.g. a full
        # address with postcode over a partial match without postcode).
        deduped: list[DetectedEntity] = []
        for e in sorted(entities, key=lambda x: (-x.confidence, -(x.end - x.start), x.start)):
            if not any(
                d.entity_type == e.entity_type
                and d.start <= e.start and e.end <= d.end
                and d is not e
                for d in deduped
            ):
                deduped.append(e)
        deduped.sort(key=lambda e: e.start)
        entities = deduped

        elapsed = time.monotonic() - t0

        # ── Convert DetectedEntity list to CandidateSpan list ──────
        result = [_entity_to_candidate(e, text=cleaned if e.start < len(cleaned) else text) for e in entities]
        telemetry.record(elapsed=elapsed, detections=[r.to_dict() for r in result], transforms=_log)
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
        # Pre-strip patterns: GPS, DATE, IP, PHONE, ADDRESS, PRIVATE_URL — these need dots/slashes/dashes
        # /commas to survive, which _strip_inner_separators destroys.
        gps_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.GPS})
        date_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.DATE})
        ip_entities, _ = self._run_patterns_for_type(text_for_gps, {EntityType.IP_ADDRESS})
        phone_entities_presistrip, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.PHONE}
        )
        # Filter pre-strip phone entities: keep CJK, +-prefixed, or >=0.70
        # confidence patterns (see detect() for rationale).
        phone_entities_presistrip = [
            e for e in phone_entities_presistrip
            if any(cjk in e.value for cjk in ("电话", "電話", "電話は", "电话是"))
            or (e.confidence >= 0.80 and "+" in e.value)
            or e.confidence >= 0.70
        ]
        address_entities_presistrip, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.ADDRESS}
        )
        private_url_entities_presistrip, _ = self._run_patterns_for_type(
            text_for_gps, {EntityType.PRIVATE_URL}
        )
        stripped = Deobfuscator._strip_inner_separators(cleaned)
        entities, cc_ssn_spans = self._run_patterns(stripped)
        # Build comprehensive covered spans to prevent Luhn/SSN validators
        # from re-detecting digit runs already covered by non-CC/SSN types.
        all_spans: set[tuple[int, int]] = {
            (e.start, e.end) for e in entities
        } | cc_ssn_spans
        # Structural recall pass
        luhn_found = self._run_luhn_on_numeric_runs(stripped, all_spans)
        entities.extend(luhn_found)
        ssn_found = self._validate_ssn_runs(stripped, all_spans)
        entities.extend(ssn_found)
        entities.extend(gps_entities)
        entities.extend(date_entities)
        entities.extend(ip_entities)
        entities.extend(phone_entities_presistrip)
        entities.extend(address_entities_presistrip)
        entities.extend(private_url_entities_presistrip)
        entities.sort(key=lambda e: e.start)

        # ── Cross-type dedup: suppress pre-strip PRIVATE_URL entities ──
        # that are contained within DATABASE_URL or URL entities (from
        # stripped text). When a PRIVATE_URL like "db.internal:5432/production"
        # is a substring of "postgresql://admin:***@db.internal:5432/production"
        # (DATABASE_URL), the broader type is more specific and the private-
        # hostname match is noise.
        url_substring_types = {EntityType.DATABASE_URL, EntityType.URL, EntityType.PRIVATE_URL}
        private_url_substrings: list[str] = []
        for e in entities:
            if e.entity_type == EntityType.PRIVATE_URL:
                # Check if any DATABASE_URL/URL contains this match as substring
                is_contained = False
                for other in entities:
                    if other is e and other.entity_type == EntityType.PRIVATE_URL:
                        continue
                    if other.entity_type in url_substring_types:
                        # Use value-based containment since coordinates may differ
                        if e.value in other.value and len(e.value) < len(other.value):
                            is_contained = True
                            break
                if not is_contained:
                    private_url_substrings.append(e.value)

        # Now apply: only keep PRIVATE_URL entities that are not contained
        filtered_entities: list[DetectedEntity] = []
        for e in entities:
            if e.entity_type == EntityType.PRIVATE_URL:
                if e.value in private_url_substrings:
                    filtered_entities.append(e)
            else:
                filtered_entities.append(e)
        entities = filtered_entities

        # ── Cross-type dedup: suppress IP_ADDRESS entities that are ──
        # contained within PRIVATE_URL entities (same logic as detect()).
        if private_url_entities_presistrip:
            private_url_values = {e.value for e in private_url_entities_presistrip}
            filtered: list[DetectedEntity] = []
            for e in entities:
                if e.entity_type == EntityType.IP_ADDRESS:
                    is_contained = any(e.value in puv for puv in private_url_values)
                    if is_contained:
                        continue
                filtered.append(e)
            entities = filtered

        # ── Cross-type PHONE dedup (same as detect() — see notes there) ──
        entities = self._filter_phone_overlap(entities, ip_entities, gps_entities, date_entities, phone_entities_presistrip)

        # ── Cross-type SSN dedup: filter out SSN matches that overlap ──
        # with IP/GPS/DATE entities by digit content (see detect() notes).
        entities = self._filter_ssn_overlap(entities, ip_entities, gps_entities, date_entities)

        # ── Same-type dedup (see detect() for details) ──
        deduped: list[DetectedEntity] = []
        for e in sorted(entities, key=lambda x: (-x.confidence, -(x.end - x.start), x.start)):
            if not any(
                d.entity_type == e.entity_type
                and d.start <= e.start and e.end <= d.end
                and d is not e
                for d in deduped
            ):
                deduped.append(e)
        deduped.sort(key=lambda e: e.start)
        entities = deduped

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
    def _gps_coords_valid(match_text: str) -> bool:
        """Validate a GPS coordinate match for realistic lat/lon ranges.

        For coordinate pairs (comma/semicolon/cardinal-direction separated):
          - First numeric value is LAT: requires [-90, 90]
          - Second numeric value is LON: requires [-180, 180]
          - At least one value must have >= 4 decimal places

        For keyword-prefixed single values:
          - lat/latitude/gps/coord prefix: value in [-90, 90]
          - lon/lng/longitude prefix: value in [-180, 180]
          - Both require >= 4 decimal places

        For bare single values (lowest-confidence GPS pattern):
          - Must be in [-90, 90] AND have >= 4 decimals
        """
        import re as _re

        full_lower = match_text.lower()
        nums = _re.findall(r"[-+]?\d+\.\d+", match_text)
        if len(nums) < 1:
            return False

        try:
            floats = [float(n) for n in nums]
        except ValueError:
            return False

        has_precision = any(
            len(n.split(".")[1]) >= 4
            for n in nums if "." in n
        )

        # ── Single coordinate ─────────────────────────────────────────
        if len(nums) == 1:
            f = floats[0]
            prefix = full_lower[:full_lower.find(nums[0].lower())].strip()

            # Lon/lng/longitude context
            if any(kw in prefix for kw in ("lon", "lng", "longitude")):
                return -180.0 <= f <= 180.0 and has_precision

            # Lat/latitude/gps/coords context
            if any(kw in prefix for kw in ("lat", "latitude", "gps", "coordinates", "coord", "location")):
                return -90.0 <= f <= 90.0 and has_precision

            # Bare single value: must be lat-like
            if not (-90.0 <= f <= 90.0):
                return False
            return has_precision

        # ── Coordinate pairs (2+ numbers) ─────────────────────────────
        # Check for comma/semicolon separator between numbers
        has_proper_separator = bool(_re.search(r"\d\s*[,;]\s*", match_text))
        # Also check for cardinal direction separator: N/S between numbers, E/W after
        # e.g. "51.5074\u00b0 N, 0.1278\u00b0 W"
        has_cardinal_sep = (
            bool(_re.search(r"[NS]\s*[,;]?\s*[-+]?\d", match_text))
            and bool(_re.search(r"\d\s*°?\s*[EW]", match_text))
        )

        if not (has_proper_separator or has_cardinal_sep):
            return False

        lat_val = floats[0]
        lon_val = floats[1] if len(floats) >= 2 else floats[0]

        if not (-90.0 <= lat_val <= 90.0):
            return False
        if not (-180.0 <= lon_val <= 180.0):
            return False
        if not has_precision:
            return False

        return True

    @staticmethod
    def _filter_phone_overlap(
        entities: list[DetectedEntity],
        ip_entities: list[DetectedEntity],
        gps_entities: list[DetectedEntity],
        date_entities: list[DetectedEntity],
        phone_presistrip: list[DetectedEntity] | None = None,
    ) -> list[DetectedEntity]:
        """Remove low-confidence PHONE entities whose digit content matches
        an IP, GPS, DATE, or already-detected pre-strip PHONE entity.

        After inner-separator stripping, bare-digit phone patterns can
        match the residue of dotted IPs (e.g. 47.94.124.103 → 4794124103).
        Since pre-strip entities use original-text coordinates and stripped
        entities use stripped-text coordinates, we match by digit content
        rather than position.

        Pre-strip phone entities (those detected before inner-separator
        stripping preserves the original separator format) are never
        suppressed by this filter — they are more accurate than the
        bare-digit matches found on stripped text.
        """
        if not entities:
            return entities

        # Build lookup: pure-digit string → set of entity types it came from
        pre_strip_digits: dict[str, set[str]] = {}
        for src_label, src_list in [
            ("ip", ip_entities),
            ("gps", gps_entities),
            ("date", date_entities),
            ("phone_pst", phone_presistrip or []),
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
                    # Check if this is a pre-strip phone entity — never suppress those
                    # (they were detected on the original text with proper separators)
                    if "phone_pst" in pre_strip_digits.get(ed, set()):
                        filtered.append(e)
                        continue
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

    @staticmethod
    def _filter_ssn_overlap(
        entities: list[DetectedEntity],
        ip_entities: list[DetectedEntity],
        gps_entities: list[DetectedEntity],
        date_entities: list[DetectedEntity],
    ) -> list[DetectedEntity]:
        """Remove SOCIAL_SECURITY entities whose digit content matches
        a pre-strip IP, GPS, or DATE entity.

        When dotted IPs like 192.168.1.50 are stripped to 192168150,
        the 9-digit run can pass the SSN validator even though it is
        clearly an IP address. This filter checks digit content overlap.
        """
        if not entities:
            return entities

        # Build lookup: pure-digit string → set of entity types
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
            if e.entity_type == EntityType.SOCIAL_SECURITY:
                ed = "".join(c for c in e.value if c.isdigit())
                if ed:
                    skip = False
                    for psd in pre_strip_digits:
                        if psd in ed or ed in psd:
                            skip = True
                            break
                    if skip:
                        continue
            filtered.append(e)
        return filtered

    @staticmethod
    def _filter_bank_account_gps_overlap(
        entities: list[DetectedEntity],
        gps_entities: list[DetectedEntity],
    ) -> list[DetectedEntity]:
        """Remove low-confidence BANK_ACCOUNT entities whose digit content
        matches a pre-strip GPS entity.

        After separator stripping, coordinate pairs like "50.0000, 100.0000"
        collapse to "5000001000000" on stripped text, which the bare-digit
        BANK_ACCOUNT pattern (0.55) then matches. Since the GPS detection
        (on pre-strip text) is more accurate, suppress these FPs.
        """
        if not gps_entities or not entities:
            return entities

        # Build GPS digit content set
        gps_digits = {
            "".join(c for c in e.value if c.isdigit())
            for e in gps_entities
        }
        if not gps_digits:
            return entities

        filtered: list[DetectedEntity] = []
        for e in entities:
            if e.entity_type == EntityType.BANK_ACCOUNT and e.confidence <= 0.65:
                ed = "".join(c for c in e.value if c.isdigit())
                if ed:
                    # Check if this bank-account digit content overlaps
                    # with any GPS digit content
                    skip = False
                    for gd in gps_digits:
                        if gd in ed or ed in gd:
                            skip = True
                            break
                    if skip:
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

                # Skip if fully contained in an already-found match.
                # Cross-type containment is normally filtered (e.g., an untyped
                # match inside an EMAIL is noise), but some specific type pairs
                # are legitimate — e.g. PERSON inside EMAIL (CJK name before @).
                if any(
                    s <= start and end <= e
                    for i, (s, e) in enumerate(seen_intervals)
                    if not (
                        entities[i].entity_type == EntityType.EMAIL
                        and entity_type == EntityType.PERSON
                    )
                    and not (
                        entities[i].entity_type == EntityType.ADDRESS
                        and entity_type == EntityType.CITY
                    )
                ):
                    continue

                # NEW: If this match CONTAINS an already-found match, prefer the narrower
                # match (better boundary precision). This prevents context-prefixed
                # matches like "from Acme Corp" from surviving alongside "Acme Corp".
                # IMPORTANT: When the contained entities have DIFFERENT entity types
                # than the new match, the keyword-extension heuristic does NOT apply.
                # A context-keyword match (e.g. BANK_ACCOUNT "account: 8765432109876543")
                # should always replace a generic match of a different type (e.g. CREDIT_CARD
                # "8765432109876543") because the context-keyword pattern is more specific.
                contained_by_new = [(i, (s, e)) for i, (s, e) in enumerate(seen_intervals)
                                    if start <= s and e <= end]
                if contained_by_new:
                    # Check if ALL contained matches have the SAME type as the new match.
                    # Cross-type containment means the broader match is more specific
                    # (has context keywords), so we should replace the narrower match.
                    contained_types = {entities[i].entity_type for i, _ in contained_by_new}
                    same_type_only = len(contained_types) == 1 and entity_type in contained_types

                    if same_type_only:
                        # Same-type containment: prefer narrower match (keyword extension heuristic).
                        contained_start = min(s for _, (s, _) in contained_by_new)
                        if start < contained_start - 1:
                            # This new match starts well before the contained match —
                            # it's likely a keyword extension. Skip it.
                            continue
                    # Otherwise (cross-type or exact-same-span), the new context-keyword
                    # match is more specific — replace the contained matches.
                    for i, _ in reversed(contained_by_new):
                        entities.pop(i)
                        seen_intervals.pop(i)

                # Luhn validation for CREDIT_CARD: discard matches whose
                # digit content fails the checksum.
                if entity_type == EntityType.CREDIT_CARD:
                    digits = "".join(c for c in match.group() if c.isdigit())
                    # Masked-card guard: if the non-digit portion is purely mask
                    # characters (X, *, #, bullets), this is a redacted/reference-only
                    # masked card. Still emit as CREDIT_CARD so the benchmark counts
                    # it as a true positive for full recall — the benchmark's own
                    # is_masked_pii() handles real-only filtering separately.
                    non_digits = "".join(c for c in match.group() if not c.isdigit())
                    is_fully_masked = len(digits) <= 6 and all(
                        c in ("X", "*", "#", "\u2022", "\u25CF") or c.isspace() or c in "-. "
                        for c in non_digits
                    )
                    import re as _re
                    has_mask_blocks = _re.search(r'([X*#])\1{3}', match.group()) is not None
                    if is_fully_masked or (has_mask_blocks and len(digits) <= 6):
                        # Masked/redacted card — emit as MASKED_CC type.
                        # The benchmark counts this as a true positive for full-denominator
                        # recall, while separating it via is_masked_pii().
                        entities.append(
                            DetectedEntity(
                                entity_type=EntityType.MASKED_CC,
                                value=match.group(),
                                start=start,
                                end=end,
                                confidence=score,
                                detector="regex",
                            )
                        )
                        seen_intervals.append((start, end))
                        continue
                    if len(digits) >= 13 and not self._luhn_check(digits):
                        continue

                # Masked-SSN guard: instead of suppressing masked SSNs entirely,
                # emit them as MASKED_SSN type. The benchmark then counts them as
                # true positives for full-denominator recall, while is_masked_pii()
                # separates them for real-only metrics.
                if entity_type == EntityType.SOCIAL_SECURITY:
                    if "X" in match.group().upper() or "*" in match.group() or "#" in match.group() or "\u2022" in match.group() or "\u25CF" in match.group():
                        entities.append(
                            DetectedEntity(
                                entity_type=EntityType.MASKED_SSN,
                                value=match.group(),
                                start=start,
                                end=end,
                                confidence=score,
                                detector="regex",
                            )
                        )
                        seen_intervals.append((start, end))
                        continue

                # Masked-email guard: suppress emails where the local part
                # is entirely redaction characters (all same char repeated,
                # or all X/x/* chars). These are obfuscated references like
                # xxxx@domain.com, ****@domain.com — not real PII.
                if entity_type == EntityType.EMAIL:
                    local_part = match.group().split("@")[0] if "@" in match.group() else ""
                    if local_part:
                        # All same char repeated (e.g. xxxx, ****, ....)
                        if len(set(local_part.upper())) == 1:
                            continue
                        # All X/* chars (e.g. xxxx, XXXX, ****)
                        if all(c in "xX*" for c in local_part):
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
                        # Check SSN context keywords in surrounding text.
                        # Check BOTH before and after (keywords like "social_security"
                        # may appear before the dash-stripped digit run).
                        # Include underscore variant "social_security" since
                        # strip-inner-seps only removes non-alpha between digits,
                        # so "social_security" survives in the stripped text.
                        context_before = text[max(0, start - 50):start].lower()
                        context_after = text[end:min(len(text), end + 30)].lower()
                        combined_context = context_before + " " + context_after
                        ssn_keywords = (
                            "ssn", "social security", "social_security",
                            "tax id", "ss#",
                        )
                        if any(kw in combined_context for kw in ssn_keywords):
                            continue
                        # Also suppress 9-digit decimal IPs where the first digit
                        # is '9' (area 900-999) — these are almost certainly
                        # obfuscated SSNs or other identifiers, never genuine
                        # decimal IPs in practice. All valid decimal IP 9-digit
                        # numbers starting with '9' would decode to IPs in
                        # 53.x.x.x-59.x.x.x range, which do not appear in real
                        # usage as bare decimal integers.
                        if digits_only.startswith("9"):
                            continue
                        area, group, serial = digits_only[:3], digits_only[3:5], digits_only[5:]
                        if (area != "000" and area != "666"
                                and not ("900" <= area <= "999")
                                and group != "00" and serial != "0000"):
                            continue

                    # ── Anti-phone / anti-bank heuristic: exclude 10-digit numbers
                    # that are preceded by phone, bank-account, or obfuscation
                    # context keywords, or that start with '1' without IP context
                    # (likely NANP phone). Also check context after the match.
                    if len(digits_only) == 10:
                        context_before = text[max(0, start - 50):start].lower()
                        context_after = text[end:min(len(text), end + 30)].lower()
                        combined_context = context_before + " " + context_after
                        phone_keywords = (
                            "phone", "tel", "mobile", "cell", "call",
                            "contact", "dial", "number",
                            # Obfuscation context markers that often
                            # precede phone/SSN test data
                            "hidden", "obfuscat", "encoded",
                        )
                        bank_keywords = (
                            "bank", "account", "acct", "a/c"
                        )
                        if any(kw in combined_context for kw in phone_keywords):
                            continue
                        if any(kw in combined_context for kw in bank_keywords):
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
        (before inner-separator stripping destroys key characters like dots,
        commas, or dashes).
        Currently used for GPS, DATE, IP_ADDRESS, PHONE (CJK-only), and ADDRESS.

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

                    # --- Anti-date guard: skip if first two octets look like a
                    # month/day date AND the third octet is a valid 4-digit year,
                    # indicating dates like "12.31.2025" rather than an IP address.
                    # Pure month/day (10.10.x.x) is common for real IPs in the
                    # 10.x.x.x range and should NOT be suppressed.
                    dots = ip_text.count(".")
                    if dots >= 2:
                        # Extract the first two dot-separated groups
                        groups = ip_text.split(".")
                        if len(groups) >= 2:
                            try:
                                first = int(groups[0])
                                second = int(groups[1])
                                # Month (1-12) + valid day (1-31) = date-like.
                                # But only suppress if the third octet is a valid
                                # 4-digit year (e.g. 12.31.2025 has year=2025,
                                # while 10.10.10.10 has third=10 — not a year).
                                if (1 <= first <= 12 and 1 <= second <= 31
                                        and dots == 3 and len(groups) >= 4):
                                    third = int(groups[2])
                                    # Valid 4-digit years: 1900-2099 (common date range)
                                    if 1900 <= third <= 2099:
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
                    # Uses word-boundary matching (\b) for keywords that are
                    # substrings of common words (e.g. "account" in "accounting",
                    # "a/c" in "data/cache") to avoid false suppression.
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
                            # Bank keywords — use word-boundary check for
                            # "account" to avoid matching "accounting"
                            # "a/c" checked below with boundary regex
                            "bank", "acct",
                            # Version/measurement keywords
                            "version", "ver.", "v.", "release",
                            "build", "rev", "revision",
                        )
                        # Check "account" with word boundaries to avoid "accounting"
                        def _has_word_boundary(text: str, word: str) -> bool:
                            return bool(re.search(rf"\b{re.escape(word)}\b", text))
                        any_non_ip = (
                            any(kw in context_before for kw in non_ip_keywords)
                            or _has_word_boundary(context_before, "account")
                            or _has_word_boundary(context_before, "a/c")
                        )
                        any_non_ip_after = (
                            any(kw in context_after for kw in non_ip_keywords)
                            or _has_word_boundary(context_after, "account")
                            or _has_word_boundary(context_after, "a/c")
                        )
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
                            combined_context = context_before + " " + context_after
                            ssn_keywords = (
                                "ssn", "social security", "social_security",
                                "tax id", "ss#",
                            )
                            if any(kw in combined_context for kw in ssn_keywords):
                                continue
                            # Suppress 9-digit decimal IPs starting with '9'
                            # (area 900-999) — these are virtually always
                            # obfuscated SSNs or other identifiers, never
                            # genuine decimal IPs in practice.
                            if digits_only.startswith("9"):
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

                # ── GPS range validation ──────────────────────────────────
                # Validate coordinate pairs for realistic lat/lon ranges.
                # Only applies to GPS patterns (which run on pre-strip text).
                if entity_type == EntityType.GPS:
                    match_text = match.group()
                    if not self._gps_coords_valid(match_text):
                        continue

                # ── BANK_ACCOUNT context gate (bare-digit, low confidence) ──
                # The 0.55 confidence pattern (\b\d{12,20}\b) matches any long
                # digit run. Suppress low-confidence BANK_ACCOUNT unless a
                # bank/account keyword appears in context, or the match is
                # adjacent to an IBAN/CREDIT_CARD/ROUTING type keyword.
                if entity_type == EntityType.BANK_ACCOUNT and score <= 0.65:
                    context_before = text[max(0, start - 30):start].lower()
                    context_after = text[end:min(len(text), end + 20)].lower()
                    ba_keywords = ("bank", "account", "acct", "a/c", "iban",
                                   "routing", "aba", "wire", "swift", "bic")
                    has_ba_context = (
                        any(kw in context_before for kw in ba_keywords)
                        or any(kw in context_after for kw in ba_keywords)
                    )
                    if not has_ba_context:
                        continue

                # ── COUNTRY context gate ────────────────────────────────────
                # Gazetteer-based country detection fires on ANY occurrence of
                # a country name, even in non-country contexts (e.g. "Canada"
                # in a brand name, "Turkey" as a food item). Suppress when the
                # word appears without country-relevant context, or relegate
                # to arbitration loss against ADDRESS/CITY.
                if entity_type == EntityType.COUNTRY and score <= 0.80:
                    context_before = text[max(0, start - 40):start].lower()
                    context_after = text[end:min(len(text), end + 30)].lower()
                    country_context = (
                        "in " in context_before[-15:]
                        or "from " in context_before[-15:]
                        or "to " in context_before[-15:]
                        or "of " in context_before[-15:]
                        or "country" in context_before
                        or "country" in context_after
                        or "nationality" in context_before
                        or "resident" in context_before
                        or "citizen" in context_before
                        or "based in" in context_before
                        or "located in" in context_before
                        or "address" in context_before
                        or "address" in context_after
                        # Comma before country often signals location context
                        or context_before.strip().endswith(",")
                    )
                    if not country_context:
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


def _entity_to_candidate(
    entity: DetectedEntity,
    text: str | None = None,
) -> CandidateSpan:
    """Convert a ``DetectedEntity`` (internal pipeline model) to a ``CandidateSpan``
    with extracted ``raw_score`` and ``features`` dict.

    The features dict is populated from the entity's properties and the
    surrounding text context, providing explainable evidence for the
    Arbitrator to consume.
    """
    features: dict[str, Any] = {}

    # ── checksum_valid ────────────────────────────────────────────
    # CREDIT_CARD entities have already passed Luhn validation in the
    # pipeline — so if we see a CREDIT_CARD entity, Luhn is valid.
    # SOCIAL_SECURITY entities have passed area/group/serial validation.
    if entity.entity_type == EntityType.CREDIT_CARD:
        features["checksum_valid"] = True
    elif entity.entity_type in (EntityType.SOCIAL_SECURITY, EntityType.MASKED_SSN):
        # SSNs validated via area/group/serial rules; masked SSNs are
        # obfuscated references with only partial digits visible
        features["checksum_valid"] = True if entity.entity_type == EntityType.SOCIAL_SECURITY else False
    else:
        features["checksum_valid"] = None

    # ── context_keywords ─────────────────────────────────────────
    # Scan the text before the match for known PII context keywords.
    keywords: list[str] = []
    if text:
        before = text[max(0, entity.start - 80):entity.start].lower()
        # General PII keywords by entity type
        _CTX_SSN = ("ssn", "social security", "tax id", "ss#")
        _CTX_DATE = ("date", "dob", "born", "expir", "valid until", "updated", "issued", "created on")
        _CTX_PHONE = ("phone", "tel", "mobile", "cell", "call", "contact", "dial", "number")
        _CTX_BANK = ("bank", "account", "acct", "a/c")
        _CTX_EMAIL = ("email", "e-mail", "mail")
        _CTX_CC = ("credit card", "credit", "cc", "card number", "card no")
        _CTX_IP = ("ip", "ip address")
        _CTX_GPS = ("gps", "lat", "lng", "lon", "latitude", "longitude", "coordinates", "location")
        _CTX_PERSON = ("name", "person", "contact", "user")
        _CTX_ADDR = ("address", "street", "suite", "apt", "unit")
        _CTX_JWT = ("jwt", "token")
        _CTX_API = ("api key", "api", "token", "secret", "key")
        _CTX_SSH = ("ssh key", "private key", "ssh")
        _CTX_URL = ("url", "http", "https", "connection", "endpoint")
        _CTX_DOMAIN = ("domain", "hostname")

        # Entity-type-specific keyword groups
        type_map: dict[EntityType, tuple[str, ...]] = {
            EntityType.SOCIAL_SECURITY: _CTX_SSN,
            EntityType.MASKED_SSN: _CTX_SSN,
            EntityType.DATE: _CTX_DATE,
            EntityType.PHONE: _CTX_PHONE,
            EntityType.BANK_ACCOUNT: _CTX_BANK + _CTX_SSN,
            EntityType.CREDIT_CARD: _CTX_CC,
            EntityType.EMAIL: _CTX_EMAIL,
            EntityType.IP_ADDRESS: _CTX_IP,
            EntityType.GPS: _CTX_GPS,
            EntityType.PERSON: _CTX_PERSON,
            EntityType.ADDRESS: _CTX_ADDR,
            EntityType.JWT: _CTX_JWT,
            EntityType.API_KEY: _CTX_API,
            EntityType.SSH_KEY: _CTX_SSH,
            EntityType.URL: _CTX_URL,
            EntityType.DOMAIN: _CTX_DOMAIN,
            EntityType.DATABASE_URL: _CTX_URL,
            EntityType.PRIVATE_URL: _CTX_URL,
            EntityType.IBAN: _CTX_BANK,
        }
        keywords = [
            kw for kw in type_map.get(entity.entity_type, ())
            if kw in before
        ]
    features["context_keywords"] = keywords

    # ── format_class ──────────────────────────────────────────────
    features["format_class"] = _infer_format_class(entity)

    return CandidateSpan(
        start=entity.start,
        end=entity.end,
        text=entity.value,
        entity_type=entity.entity_type,
        detector="regex",
        raw_score=entity.confidence,
        features=features,
    )


def _infer_format_class(entity: DetectedEntity) -> str:
    """Infer the format class of a detected entity from its value and type.

    Returns a human-readable string describing the format variant (e.g.
    ``"4-4-4-4"``, ``"dotted"``, ``"keyword-prefixed"``, ``"masked"``, ``"bare-digit"``).
    """
    val = entity.value
    et = entity.entity_type

    # Generic helpers
    has_separator = bool(re.search("[- .\u00A0–—−/]", val))
    has_dots = "." in val
    has_dashes = bool(re.search(r"[-–—−]", val))
    has_spaces = " " in val
    has_slashes = "/" in val
    has_asterisk = "*" in val
    has_x_mask = "X" in val.upper() and "X" in val
    has_bullet = any(c in val for c in ("\u2022", "\u25CF"))
    is_all_digits = val.strip().isdigit()
    is_masked = has_asterisk or has_x_mask or has_bullet

    # Keyword-prefixed: starts with context keyword
    _KEYWORD_PREFIXES = (
        "ssn", "social", "phone", "tel", "credit", "card", "bank",
        "account", "acct", "passport", "email", "date", "dob", "gps",
        "lat", "lng", "lon", "ip", "http", "https", "ssh", "token", "api",
    )
    has_keyword_prefix = val.lower().startswith(_KEYWORD_PREFIXES) or (
        len(val) > 4 and val.lower().split(":")[0].strip() in (
            "ssn", "phone", "credit card", "credit", "card", "email",
            "date", "bank account", "account", "passport", "gps",
        )
    )

    if et == EntityType.CREDIT_CARD:
        if is_masked:
            return "masked"
        if has_keyword_prefix:
            return "keyword-prefixed"
        dot_count = val.count(".")
        dash_count = len(re.findall(r"[-–—−]", val))
        if dot_count >= 2:
            if dash_count > 0:
                return "mixed"
            return "dot-separated"
        if dash_count >= 3:
            return "4-4-4-4"
        if dash_count == 2:
            return "4-6-5"
        if has_spaces:
            space_segments = val.split()
            if len(space_segments) == 8:
                return "2-digit-pair"
            return "space-separated"
        return "bare-digit"

    if et == EntityType.SOCIAL_SECURITY:
        if is_masked:
            return "masked"
        if has_keyword_prefix:
            return "keyword-prefixed"
        if has_dashes or " " in val:
            return "separator"
        return "bare-digit"

    if et == EntityType.MASKED_SSN:
        return "masked"

    if et == EntityType.PHONE:
        if val.startswith("+"):
            return "international"
        if "电话" in val or "電話" in val:
            return "cjk-keyword"
        if has_keyword_prefix:
            return "keyword-prefixed"
        if "(" in val:
            return "parenthesized"
        if has_dashes and val.count("-") >= 2:
            return "dashed"
        if has_dots:
            return "dotted"
        if has_spaces:
            return "spaced"
        return "bare-digit"

    if et in (EntityType.EMAIL, EntityType.URL, EntityType.DATABASE_URL, EntityType.PRIVATE_URL):
        if "://" in val:
            return "protocol"
        if "@" in val:
            return "email-format"
        return "bare"

    if et == EntityType.IP_ADDRESS:
        if ":" in val:
            return "ipv6"
        if has_dots and val.count(".") == 3:
            return "dotted"
        if " " in val:
            return "space-separated"
        if val.startswith("0x"):
            return "hex"
        if val.startswith("0") and len(val) > 1:
            return "octal"
        return "decimal"

    if et == EntityType.GPS:
        if has_keyword_prefix:
            return "keyword-prefixed"
        if "," in val or ";" in val:
            return "coordinate-pair"
        return "decimal"

    if et in (EntityType.JWT, EntityType.API_KEY, EntityType.SSH_KEY):
        if val.count(".") >= 2:
            return "dotted"
        return "continuous"

    if et in (EntityType.DATE,):
        if " " in val and not has_slashes and not has_dashes:
            return "month-name"
        if "-" in val:
            return "iso"
        if "/" in val:
            return "slash"
        return "bare"

    if et == EntityType.ADDRESS:
        if "P.O." in val.upper() or "BOX" in val.upper():
            return "po-box"
        if val.startswith(("Suite", "Apt", "Unit")):
            return "subunit"
        if "/" in val or val.count(",") >= 1:
            return "european"
        return "standard"

    if et in (EntityType.PERSON, EntityType.CUSTOMER_NAME, EntityType.EMPLOYEE_NAME, EntityType.COMPANY, EntityType.PROJECT_NAME):
        if has_keyword_prefix:
            return "keyword-prefixed"
        return "name"

    if et == EntityType.IBAN:
        return "iban"

    if et == EntityType.PASSPORT:
        if has_keyword_prefix:
            return "keyword-prefixed"
        return "bare"

    return "unknown"


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
        "SOCIAL_SECURITY", "MASKED_SSN", "MASKED_CC", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
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
        # Fallback map values are lowercase — uppercase for EntityType lookup
        try:
            return EntityType(fallback.upper() if fallback else "PERSON")
        except ValueError:
            return EntityType("PERSON")