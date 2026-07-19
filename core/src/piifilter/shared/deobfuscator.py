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

_SPOKEN_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "oh": "0",
}
# Build regex that matches spoken numbers as whole words
_SPOKEN_RE = re.compile(
    r"\b(?:" + "|".join(_SPOKEN_NUMBERS.keys()) + r")\b",
    re.IGNORECASE,
)


def _replace_spoken(m: re.Match[str]) -> str:
    return _SPOKEN_NUMBERS.get(m.group(0).lower(), m.group(0))


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
        """Convert spoken number words (one, two, … nine) to digits.

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