"""Deobfuscator — normalizes common PII evasion patterns before detection.

Transforms obfuscated formats back to canonical form so regex patterns
can match them. NFKC normalization is applied first, then pattern transforms.

Transforms implemented:
1. NFKC normalization (Unicode normalization form KC)
2. [at]/[dot] → @/.  (bracket, paren, angle, brace variants, with/without spaces)
3. HTML entities → decoded characters (&#NNN; and &#xHH; for ASCII printable)
4. Zero-width characters removed (ZWSP, ZWNJ, ZWJ)
5. Unicode dashes → standard hyphen-minus
6. Soft hyphens removed
7. Fullwidth ASCII (FF01-FF5E) → standard ASCII
8. Unicode escape sequences (\\uXXXX) → actual characters
9. URL percent-encoding (%XX) decoded for PII-relevant chars (@, ., -, _, etc.)
10. Spoken numbers → digits (one→1, two→2, etc.) for phone/SSN/ip patterns
"""

from __future__ import annotations

import base64
import re
import unicodedata

# ── HTML entity decoder ──────────────────────────────────────────────────────

_HTML_DECIMAL_RE = re.compile(r"&#(\d{1,5});")
_HTML_HEX_RE = re.compile(r"&#[xX]([0-9a-fA-F]{1,6});")

_DECODE_CACHE: dict[int, str] = {}


def _decode_codepoint(cp: int) -> str:
    """Decode a codepoint, caching results and clamping to ASCII printable-ish range."""
    if cp not in _DECODE_CACHE:
        if cp < 0x80 or (0xA0 <= cp <= 0xFF):
            _DECODE_CACHE[cp] = chr(cp)
        elif 0x80 <= cp < 0xA0:
            # C1 control characters — replace with space to avoid introducing
            # non-printable chars
            _DECODE_CACHE[cp] = "\u0020"
        else:
            # Beyond Latin-1 supplement — keep as-is (though the main use case
            # for PII deobfuscation is ASCII range)
            _DECODE_CACHE[cp] = chr(cp)
    return _DECODE_CACHE[cp]


def _replace_decimal(m: re.Match[str]) -> str:
    return _decode_codepoint(int(m.group(1)))


def _replace_hex(m: re.Match[str]) -> str:
    return _decode_codepoint(int(m.group(1), 16))


# ── Fullwidth conversion table ───────────────────────────────────────────────

# Map fullwidth ASCII range (U+FF01-U+FF5E) to standard ASCII (0x21-0x7E)
_FULLWIDTH_ASCII = str.maketrans(
    {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)}
)


# ── Spoken number mapping ─────────────────────────────────────────────────────

_SPOKEN_SINGLE = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "oh": "0",
}
# Build regex that matches spoken number words as whole words
_SPOKEN_RE = re.compile(
    r"\b(?:" + "|".join(_SPOKEN_SINGLE.keys()) + r")\b",
    re.IGNORECASE,
)


def _replace_spoken(m: re.Match[str]) -> str:
    word = m.group(0).lower()
    return _SPOKEN_SINGLE.get(word, m.group(0))


# ── Dash/point mapping for spoken PII ─────────────────────────────────────────
# After spoken numbers are converted to digits, map spoken separators
_SPOKEN_SEP_RE = re.compile(r"\b(?:dash|point|dot|hyphen)\b", re.IGNORECASE)

# Hyphen maps to "-" not "." — handle separately
_HYPHEN_RE = re.compile(r"\bhyphen\b", re.IGNORECASE)

# ── Digit-space collapse for SSN/IP detection ─────────────────────────────────
# After "one two three dash four five dash six seven eight nine" becomes
# "1 2 3 dash 4 5 dash 6 7 8 9", this collapses adjacent digits:
# "1 2 3 dash 4 5 dash 6 7 8 9" -> "123 dash 45 dash 6789"
_DIGIT_SPACE_COLLAPSE_RE = re.compile(r"(?<=\d)\s+(?=\d)")

# ── SSN segment normalizer ────────────────────────────────────────────────────
# Strip spaces, tabs, underscores, NBSP, thin spaces between digit groups in SSN
# e.g. "123 45 6789" → "123-45-6789", "123_45_6789" → "123-45-6789"
_SSN_SEGMENT_RE = re.compile(
    r"\b(\d{3})[\s\u00A0\u2009\u2008\t_]+(\d{2})[\s\u00A0\u2009\u2008\t_]+(\d{4})\b"
)

# ── Credit card segment normalizer ────────────────────────────────────────────
# Normalize CC with underscores/dots/mixed separators between digit groups
# e.g. "4111_1111_1111_1111" → "4111 1111 1111 1111" (standard 4-4-4-4 with spaces)
# Handle: 4-4-4 pattern, 4-6-5 pattern (AMEX), and mixed separators
_CC_SEGMENT_RE = re.compile(
    r"\b(\d{4})[_.\s-]+(\d{4})[_.\s-]+(\d{4})[_.\s-]+(\d{4})\b"
)
_CC_AMEX_SEGMENT_RE = re.compile(
    r"\b(\d{4})[_.\s-]+(\d{6})[_.\s-]+(\d{5})\b"
)
_CC_MIXED_NORMALIZE_RE = re.compile(r"(\d)[_\-.]+(?=\d)")

# ── IP-spoken separator normalizer ────────────────────────────────────────────
# After spoken number conversion, collapse digit spaces for IP too
# E.g. "1 9 2 . 1 6 8 . 1 . 1" → "192.168.1.1"
# This runs AFTER dot/point → . mapping
_IP_NUM_COLLAPSE_RE = re.compile(r"(?<=\d)\s+(?=\.)|(?<=\.)\s+(?=\d)")

# ── Dash space cleanup for SSN ────────────────────────────────────────────────
# After "1 2 3 - 4 5 - 6 7 8 9" → "123 - 45 - 6789", remove spaces around dashes
# so SSN pattern can match "123-45-6789"
_DASH_SPACE_RE = re.compile(r"(?<=\d)\s+-\s+(?=\d)")


# ── URL percent-encoding ─────────────────────────────────────────────────────

_URL_PCT_RE = re.compile(r"%([0-9a-fA-F]{2})")


def _replace_url_pct(m: re.Match[str]) -> str:
    """Decode percent-encoded byte to character for PII-relevant chars."""
    cp = int(m.group(1), 16)
    # Decode printable ASCII and PII-relevant characters
    # Key ones: %40=@, %2E=., %2D=-, %5F=_, %2B=+, %23=#
    # Also decode hex digits that produce ASCII punctuation useful for PII
    if 0x20 <= cp <= 0x7E:
        return chr(cp)
    return m.group(0)  # keep non-printable as-is


class Deobfuscator:
    """Normalizes common PII evasion patterns.

    Apply before running regex detection to catch obfuscated PII that
    would otherwise bypass the pattern matcher.

    Usage::

        deob = Deobfuscator()
        cleaned, log = deob(text)
        entities = detector.detect(cleaned)
    """

    # ── Unicode escape: \\u0040 or \\U00000040 ─────────────────────────
    _UNICODE_ESC_4_RE = re.compile(rb"\\u([0-9a-fA-F]{4})")
    _UNICODE_ESC_8_RE = re.compile(rb"\\U([0-9a-fA-F]{8})")

    def __call__(self, text: str) -> tuple[str, list[dict]]:
        """Apply all deobfuscation transforms.

        Args:
            text: Input string potentially containing obfuscated PII.

        Returns:
            Tuple of (normalized_text, transform_log) where transform_log
            is a list of dicts describing each transform applied.
        """
        log: list[dict] = []
        text = self._nfkc_normalize(text, log)
        text = self._unwrap_at_dot(text, log)
        text = self._unwrap_html_entities(text, log)
        text = self._unwrap_zero_width(text, log)
        text = self._normalize_dashes(text, log)
        text = self._remove_soft_hyphen(text, log)
        text = self._flatten_fullwidth(text, log)
        text = self._unwrap_unicode_escapes(text, log)
        text = self._decode_url_percent(text, log)
        text = self._unwrap_spoken_numbers(text, log)
        text = self._map_spoken_separators(text, log)
        text = self._normalize_ssn_segments(text, log)
        text = self._normalize_cc_segments(text, log)
        text = self._cleanup_dash_spaces(text, log)
        text = self._collapse_digit_spaces(text, log)
        text = self._collapse_ip_spaces(text, log)
        return text, log

    # ── 1. NFKC normalization ──────────────────────────────────────────

    @staticmethod
    def _nfkc_normalize(text: str, log: list) -> str:
        n = unicodedata.normalize("NFKC", text)
        if n != text:
            log.append({
                "transform": "NFKC",
                "description": f"NFKC normalized ({len(text)}→{len(n)} chars)",
                "changed": True,
            })
        return n

    # ── 2. [at] / [dot] unwrapping ─────────────────────────────────────

    _AT_DOT_PATTERNS = [
        # Bracketed variants — these are unambiguous obfuscation markers
        (re.compile(r"\[at\]", re.IGNORECASE), "@"),
        (re.compile(r"\[dot\]", re.IGNORECASE), "."),
        (re.compile(r"\(at\)", re.IGNORECASE), "@"),
        (re.compile(r"\(dot\)", re.IGNORECASE), "."),
        (re.compile(r"\{at\}", re.IGNORECASE), "@"),
        (re.compile(r"\{dot\}", re.IGNORECASE), "."),
        (re.compile(r"<at>", re.IGNORECASE), "@"),
        (re.compile(r"<dot>", re.IGNORECASE), "."),
        # Bracket-wrapped symbols
        (re.compile(r"\[\@\]"), "@"),
        (re.compile(r"\[\.\]"), "."),
        # Umlaut variants — [ät] and [döt]
        (re.compile(r"\[ät\]", re.IGNORECASE), "@"),
        (re.compile(r"\[döt\]", re.IGNORECASE), "."),
        # Standalone uppercase (only ALL-CAPS AT/DOT — less likely in natural text)
        (re.compile(r"(?<!\w)AT(?!\w)"), "@"),
        (re.compile(r"(?<!\w)DOT(?!\w)"), "."),
    ]

    @classmethod
    def _unwrap_at_dot(cls, text: str, log: list) -> str:
        original = text
        for pattern, replacement in cls._AT_DOT_PATTERNS:
            text = pattern.sub(replacement, text)
        # Clean up spaces around newly inserted @ and . to allow email detection
        text = re.sub(r"\s+@\s+", "@", text)
        text = re.sub(r"\s+\.\s+", ".", text)
        if text != original:
            log.append({
                "transform": "at_dot",
                "description": "Unwrapped [at]/[dot] style obfuscation",
                "changed": True,
            })
        return text

    # ── 3. HTML entities ───────────────────────────────────────────────

    @classmethod
    def _unwrap_html_entities(cls, text: str, log: list) -> str:
        original = text
        text = _HTML_DECIMAL_RE.sub(_replace_decimal, text)
        text = _HTML_HEX_RE.sub(_replace_hex, text)
        if text != original:
            log.append({
                "transform": "html_entities",
                "description": "Decoded HTML entities",
                "changed": True,
            })
        return text

    # ── 4. Zero-width characters ───────────────────────────────────────

    _ZERO_WIDTH_RE = re.compile("[\u200B\u200C\u200D]")

    @classmethod
    def _unwrap_zero_width(cls, text: str, log: list) -> str:
        original = text
        text = cls._ZERO_WIDTH_RE.sub("", text)
        if text != original:
            log.append({
                "transform": "zero_width",
                "description": f"Removed {len(original) - len(text)} zero-width char(s)",
                "changed": True,
            })
        return text

    # ── Additional normalization passes ──────────────────────────────

    # Unicode dashes → standard hyphen-minus (U+2013 en-dash, U+2014 em-dash)
    _DASH_RE = re.compile("[\u2013\u2014]")
    # Soft hyphen (U+00AD) — invisible in most contexts, just remove it
    _SOFT_HYPHEN_RE = re.compile("\u00AD")

    # ── 5a. Unicode dashes → standard hyphen-minus ──────────────────────

    @classmethod
    def _normalize_dashes(cls, text: str, log: list) -> str:
        original = text
        text = cls._DASH_RE.sub("-", text)
        if text != original:
            log.append({
                "transform": "dashes",
                "description": "Normalized unicode dashes to hyphen-minus",
                "changed": True,
            })
        return text

    # ── 5b. Soft hyphen removal ─────────────────────────────────────────

    @classmethod
    def _remove_soft_hyphen(cls, text: str, log: list) -> str:
        original = text
        text = cls._SOFT_HYPHEN_RE.sub("", text)
        if text != original:
            log.append({
                "transform": "soft_hyphen",
                "description": "Removed soft hyphens",
                "changed": True,
            })
        return text

    # ── 6. Fullwidth ASCII ─────────────────────────────────────────────

    @staticmethod
    def _flatten_fullwidth(text: str, log: list) -> str:
        original = text
        text = text.translate(_FULLWIDTH_ASCII)
        if text != original:
            log.append({
                "transform": "fullwidth",
                "description": "Flattened fullwidth ASCII characters",
                "changed": True,
            })
        return text

    # ── 7. Unicode escape sequences ────────────────────────────────────

    @classmethod
    def _unwrap_unicode_escapes(cls, text: str, log: list) -> str:
        """Replace \\uXXXX / \\UXXXXXXXX escape sequences with actual chars.

        This works in two passes:
        1. If the input already has the literal backslash-u (e.g. from a
           Python string literal that was double-escaped), decode it.
        2. The regex matches when the text actually contains the 6-char
           sequence \\u0040 (backslash, 'u', then 4 hex digits).
        """
        original = text
        encoded = text.encode("utf-8")

        def _replace_esc(m: re.Match[bytes]) -> bytes:
            hex_str = m.group(1).decode("ascii")
            cp = int(hex_str, 16)
            return chr(cp).encode("utf-8")

        decoded = cls._UNICODE_ESC_4_RE.sub(_replace_esc, encoded)
        decoded = cls._UNICODE_ESC_8_RE.sub(_replace_esc, decoded)
        text = decoded.decode("utf-8")

        if text != original:
            log.append({
                "transform": "unicode_escapes",
                "description": "Decoded unicode escape sequences",
                "changed": True,
            })
        return text

    # ── 8. URL percent-encoding ─────────────────────────────────────────

    @classmethod
    def _decode_url_percent(cls, text: str, log: list) -> str:
        """Decode percent-encoded characters (%XX) relevant for PII.

        Key targets: %40 → @, %2E → ., %2D → -, %5F → _, %2B → +, %23 → #
        Also decode any printable ASCII that helps regex patterns match.
        """
        original = text
        text = _URL_PCT_RE.sub(_replace_url_pct, text)
        if text != original:
            log.append({
                "transform": "url_percent",
                "description": "Decoded URL percent-encoding",
                "changed": True,
            })
        return text

    # ── 9. Spoken numbers → digits ─────────────────────────────────────

    @classmethod
    def _unwrap_spoken_numbers(cls, text: str, log: list) -> str:
        """Convert spoken number words (one, two, … nine, twenty, thirty, etc.) to digits.

        This helps detect obfuscated SSNs, IPs, and phone numbers that
        are spoken out as words rather than written as numerals.
        """
        original = text
        text = _SPOKEN_RE.sub(_replace_spoken, text)
        if text != original:
            log.append({
                "transform": "spoken_numbers",
                "description": "Converted spoken number words to digits",
                "changed": True,
            })
        return text

    # ── 10. Map spoken separators ────────────────────────────────────

    @classmethod
    def _map_spoken_separators(cls, text: str, log: list) -> str:
        """Map spoken separators (dash, point, dot, hyphen) to their symbol equivalents.

        Runs AFTER spoken numbers have been converted to digits so that
        "one two three dash four five" → "1 2 3 - 4 5".
        """
        original = text
        # Map hyphen to "-" first (special case)
        text = _HYPHEN_RE.sub("-", text)
        # Map the rest: dash, point, dot
        text = _SPOKEN_SEP_RE.sub(lambda m: "-" if m.group(0).lower() == "dash" else ".", text)
        if text != original:
            log.append({
                "transform": "spoken_separators",
                "description": "Mapped spoken separators (dash/point/dot/hyphen) to symbols",
                "changed": True,
            })
        return text

    # ── 11. Collapse digit spaces ──────────────────────────────────────

    @classmethod
    def _collapse_digit_spaces(cls, text: str, log: list) -> str:
        """Collapse spaces between adjacent digits for SSN detection.

        After spoken number conversion, "1 2 3 - 4 5 - 6 7 8 9" becomes
        "123-45-6789" which the SSN pattern can match.
        """
        original = text
        text = _DIGIT_SPACE_COLLAPSE_RE.sub("", text)
        if text != original:
            log.append({
                "transform": "digit_collapse",
                "description": "Collapsed spaces between adjacent digits",
                "changed": True,
            })
        return text

    # ── 12. Normalize SSN segments ─────────────────────────────────────

    @classmethod
    def _normalize_ssn_segments(cls, text: str, log: list) -> str:
        """Normalize SSNs with spaces/underscores/tabs between digit groups.

        "123 45 6789" → "123-45-6789" so the SSN pattern matches.
        """
        original = text
        text = _SSN_SEGMENT_RE.sub(r"\1-\2-\3", text)
        if text != original:
            log.append({
                "transform": "ssn_segments",
                "description": "Normalized SSN segments with spaces to hyphen format",
                "changed": True,
            })
        return text

    # ── 12b. Credit card segment normalizer ───────────────────────────

    @classmethod
    def _normalize_cc_segments(cls, text: str, log: list) -> str:
        """Normalize CC numbers with underscores/dots/mixed separators.

        "4111_1111_1111_1111" → "4111 1111 1111 1111" (4-4-4-4 with spaces)
        "4111.1111.1111.1111" → "4111 1111 1111 1111"
        "4111 1111-1111 1111" → "4111 1111 1111 1111"
        "3782 822463 10005"   → (AMEX) keep as-is (already matches)
        """
        original = text
        # Only normalize underscores and dots that match known CC group patterns
        # 4-4-4-4 pattern with underscores: 4111_1111_1111_1111
        text = _CC_SEGMENT_RE.sub(r"\1 \2 \3 \4", text)
        # 4-6-5 pattern (AMEX) with underscores: 3782_822463_10005
        text = _CC_AMEX_SEGMENT_RE.sub(r"\1 \2 \3", text)
        if text != original:
            log.append({
                "transform": "cc_segments",
                "description": "Normalized CC number separators",
                "changed": True,
            })
        return text

    # ── 12c. Cleanup dash spaces ──────────────────────────────────────

    @classmethod
    def _cleanup_dash_spaces(cls, text: str, log: list) -> str:
        """Remove spaces around dashes in number sequences.

        After spoken conversion, "123 - 45 - 6789" → "123-45-6789".
        This allows the SSN pattern to match.
        """
        original = text
        text = _DASH_SPACE_RE.sub("-", text)
        if text != original:
            log.append({
                "transform": "dash_spaces",
                "description": "Removed spaces around dashes in number sequences",
                "changed": True,
            })
        return text

    # ── 13. Collapse digit spaces ──────────────────────────────────────

    @classmethod
    def _collapse_ip_spaces(cls, text: str, log: list) -> str:
        """Collapse spaces around dots in IP addresses that were spoken out.

        "1 9 2 . 1 6 8 . 1 . 1" → "192.168.1.1"
        """
        original = text
        text = _IP_NUM_COLLAPSE_RE.sub("", text)
        if text != original:
            log.append({
                "transform": "ip_collapse",
                "description": "Collapsed spaces in spoken IP addresses",
                "changed": True,
            })
        return text