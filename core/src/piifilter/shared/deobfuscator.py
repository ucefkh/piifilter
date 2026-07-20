"""Deobfuscator — normalizes common PII evasion patterns before detection.

Transforms obfuscated formats back to canonical form so regex patterns
can match them. NFKC normalization is applied first, then pattern transforms.

Transforms implemented:
1. NFKC normalization (Unicode normalization form KC)
2. Inner-separator stripping (collapse non-alpha chars between digits)
3. [at]/[dot] → @/.  (bracket, paren, angle, brace variants, with/without spaces)
4. HTML entities → decoded characters (&#NNN; and &#xHH; for ASCII printable)
5. Zero-width characters removed (ZWSP, ZWNJ, ZWJ)
6. Unicode dashes → standard hyphen-minus
7. Soft hyphens removed
8. Fullwidth ASCII (FF01-FF5E) → standard ASCII
9. Unicode escape sequences (\\uXXXX) → actual characters
10. URL percent-encoding (%XX) decoded for PII-relevant chars (@, ., -, _, etc.)
11. Spoken numbers → digits (one→1, two→2, etc.) for phone/SSN/ip patterns
12. Hex escape sequences (\\xHH → char) [NEW: Transform A]
13. Binary 8-bit decoding [NEW: Transform B]
14. Unicode fractions → decimals [NEW: Transform C]
15. Extended l33tspeak decoding [NEW: Transform D]
16. Morse code decoding [NEW: Transform E]
17. XML numeric escape decoder [NEW: Transform F]
18. Punctuation-stuffing remover [NEW: Transform G]
19. Pig latin decoder [NEW: Transform H]
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
_CC_MIXED_NORMALIZE_RE = re.compile(r"(\d)[_\-\.]+(?=\d)")

# ── IP-spoken separator normalizer ────────────────────────────────────────────
# After spoken number conversion, collapse digit spaces for IP too
# E.g. "1 9 2 . 1 6 8 . 1 . 1" → "192.168.1.1"
# This runs AFTER dot/point → . mapping
_IP_NUM_COLLAPSE_RE = re.compile(r"(?<=\d)\s+(?=\.)|(?<=\.)\s+(?=\d)")

# ── Dash space cleanup for SSN ────────────────────────────────────────────────
# After "1 2 3 - 4 5 - 6 7 8 9" → "123 - 45 - 6789", remove spaces around dashes
# so SSN pattern can match "123-45-6789"
_DASH_SPACE_RE = re.compile(r"(?<=\d)\s+-\s+(?=\d)")


# ── URL percent-encoding ─────────────────────────────────────

# SSN re-check pattern for decoded content — used by hex/base64/area-serial transforms
# Matches standard SSN (123-45-6789) and segment-separated formats
_SSN_RECHECK_RE = re.compile(r"\b\d{3}[- \u00A0.]?\d{2}[- \u00A0.]?\d{4}\b")

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
        # Base normalizations
        text = self._nfkc_normalize(text, log)
        text = self._strip_html_comments(text, log)
        # Morse code BEFORE at_dot so dots in morse (e.g. ".--") aren't destroyed
        text = self._decode_morse(text, log)
        text = self._unwrap_at_dot(text, log)
        text = self._fix_obfuscated_email_entities(text, log)
        # NEW: XML escape decoder (before HTML entity decoding)
        text = self._decode_xml_escape(text, log)
        text = self._unwrap_html_entities(text, log)
        text = self._unwrap_zero_width(text, log)
        text = self._normalize_dashes(text, log)
        text = self._remove_soft_hyphen(text, log)
        text = self._flatten_fullwidth(text, log)
        text = self._unwrap_unicode_escapes(text, log)
        # NEW: Hex escape decoder (before URL percent-decoding)
        text = self._decode_hex_escapes(text, log)
        # ── Recursive decode-until-stable loop for double-encoding ──
        # URL percent-encoding and hex-escapes can be double/triple-encoded.
        # E.g. %25%32%35 → Round 1: %25 → Round 2: %
        # Re-apply both decoders until no further changes occur, up to max 5 rounds.
        for _round in range(5):
            prev = text
            text = self._decode_url_percent(text, log)
            text = self._decode_hex_escapes(text, log)
            if text == prev:
                break
        # ── Percent-sandwiched separators ──
        # After URL decoding %25 → %, the resulting % between word characters
        # needs to become a space so COMPANY patterns can match.
        # E.g. Globex%Corporation → Globex Corporation
        text = self._normalize_pct_separator(text, log)
        # NEW: Binary strings decoded early
        text = self._decode_binary_strings(text, log)
        # NEW: Unicode fractions → digits
        text = self._normalize_unicode_fractions(text, log)
        text = self._unwrap_spoken_numbers(text, log)
        text = self._map_spoken_separators(text, log)
        text = self._normalize_ip_octet_spaces(text, log)
        text = self._normalize_ip_octet_dots(text, log)
        text = self._normalize_ssn_segments(text, log)
        text = self._normalize_cc_segments(text, log)
        text = self._cleanup_dash_spaces(text, log)
        text = self._collapse_ip_spaces(text, log)
        text = self._collapse_digit_spaces(text, log)
        # Save a copy of the text before _strip_non_alpha_seps destroys
        # decimal separators in GPS coordinates. This pre-strip text
        # is used by the detector for GPS pattern matching.
        text_for_gps = text
        text = self._strip_non_alpha_seps(text, log)
        text = self._decode_hex(text, log)
        text = self._decode_base64(text, log)
        text = self._extract_area_serial(text, log)
        text = self._reconstruct_split_tokens(text, log)
        # NEW: Reversed words — catch reversed email components and person names
        # Run BEFORE swap_case and l33t so case-shift and digit-substitution
        # don't destroy the patterns we need to match (e.g. "Doe Jane" must
        # stay as proper-case for reversed-name detection).
        text = self._decode_reversed_words(text, log)
        # NEW: Extended transforms — run late, after basic cleanup
        text = self._decode_l33t(text, log)
        text = self._remove_punctuation_stuffing(text, log)
        text = self._decode_pig_latin(text, log)
        text = self._swap_case(text, log)
        return text, log, text_for_gps

    # ── 1. NFKC normalization ──────────────────────────────────────────

    @classmethod
    def _nfkc_normalize(cls, text: str, log: list) -> str:
        original = text
        text = unicodedata.normalize("NFKC", text)
        if text != original:
            log.append({
                "transform": "nfkc_normalize",
                "description": "NFKC normalization (kills fractions, homoglyphs, fullwidth)",
                "changed": True,
            })
        return text

    # ── 1b. Strip inner separators within numeric spans ──────────────────────
    # Before regex pattern matching, collapse separators between digits
    # so runs like "1-2-3" → "123" while keeping alphabetic words intact.
    # This catches spacing/punctuation obfuscation of numeric PII (SSN, CC, phone).

    @staticmethod
    def _strip_inner_separators(text: str) -> str:
        """Strip non-alphanumeric (but keep newlines) chars between adjacent digits.

        ``re.sub(r"(\\d)[^\\w\\n]+(?=\\d)", r"\\1", text)`` collapses
        obfuscated numeric sequences like ``1-2-3`` → ``123`` while
        leaving alphabetic words and line structure intact.
        """
        return re.sub(r"(\d)[^\w\n]+(?=\d)", r"\1", text)

    # ── 1c. HTML comments ─────────────────────────────────────────────────

    _HTML_COMMENT_RE = re.compile(r"<!--.*?-->")

    @classmethod
    def _strip_html_comments(cls, text: str, log: list) -> str:
        """Strip HTML comments like <!--comment--> from the text."""
        original = text
        text = cls._HTML_COMMENT_RE.sub("", text)
        if text != original:
            log.append({
                "transform": "html_comments",
                "description": f"Stripped {len(original) - len(text)} chars of HTML comments",
                "changed": True,
            })
        return text

    # ── 1c. Obfuscated email &#046; → &#64; ──────────────────────────────

    # Some email obfuscations use &#046; (decimal 46 = period) where they
    # mean @. Since HTML entity decoding correctly turns &#046; into '.',
    # and &#46; also into '.', we must detect the pattern BEFORE decoding.
    # Pattern: word &#046; word &#46; tld → convert the first &#046; to &#64;
    _OBS_EMAIL_046_RE = re.compile(
        r"\b([a-zA-Z0-9._%+\-*]+)\s*&#046;\s*([a-zA-Z0-9\-]+(?:\s*&#46;\s*[a-zA-Z0-9\-]+)+)\b"
    )

    @classmethod
    def _fix_obfuscated_email_entities(cls, text: str, log: list) -> str:
        """Convert &#046; → &#64; when it's being used as @ in email obfuscation.

        e.g. 'alice &#046; acme &#46; com' → 'alice &#64; acme &#46; com'
        so that HTML entity decoding produces 'alice@acme.com'.
        """
        original = text

        def _fix_046(m: re.Match) -> str:
            local = m.group(1)
            domain = m.group(2)
            # The part before the &#046; is the email local part.
            # The part after &#046; but before the first &#46; is the domain name.
            # Everything after &#46; is the TLD(s).
            # We replace &#046; with &#64; (the @ sign)
            # The &#46; stays as-is (will decode to '.')
            return f"{local} &#64; {domain}"

        text = cls._OBS_EMAIL_046_RE.sub(_fix_046, text)
        if text != original:
            log.append({
                "transform": "obfuscated_email_046",
                "description": "Fixed &#046; → &#64; in obfuscated email patterns",
                "changed": True,
            })
        return text

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
        # Handle both double-sided and single-sided spaces
        text = re.sub(r"\s+@\s+", "@", text)
        text = re.sub(r"\s+@", "@", text)
        text = re.sub(r"@\s+", "@", text)
        text = re.sub(r"\s+\.\s+", ".", text)
        text = re.sub(r"\s+\.", ".", text)
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
        # Clean up spaces around @ and . that HTML entity decode may have produced
        # e.g. &#64; → @ (with no space), but the original text had spaces around
        # the encoded entity, so now we need single-sided cleanup
        text = re.sub(r"\s+@\s+", "@", text)
        text = re.sub(r"\s+@", "@", text)
        text = re.sub(r"@\s+", "@", text)
        text = re.sub(r"\s+\.\s+", ".", text)
        text = re.sub(r"\s+\.", ".", text)
        if text != original:
            log.append({
                "transform": "html_entities",
                "description": "Decoded HTML entities",
                "changed": True,
            })
        return text

    # ── 4. Zero-width characters ───────────────────────────────────────

    # Zero-width characters + BOM (byte order mark, U+FEFF)
    _ZERO_WIDTH_RE = re.compile("[\u200B\u200C\u200D\uFEFF]")

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

    # ── 11b. Strip non-alpha separators inside digit spans ──────────────

    _ALNUM_SEP_RE = re.compile(r"(\d)[^\w\n]+(?=\d)")

    @classmethod
    def _strip_non_alpha_seps(cls, text: str, log: list) -> str:
        """Strip non-alpha separators between digits (e.g. 1..2..3 -> 123)."""
        original = text
        text = cls._ALNUM_SEP_RE.sub(r"\1", text)
        if text != original:
            log.append({
                "transform": "strip_inner_seps",
                "description": "Stripped non-alpha separators inside digit spans",
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

    _IP_OCTET_SPACE_RE = re.compile(
        r"\b((?:2(?:5[0-5]|[0-4]\d)|1\d{2}|[1-9]?\d))\s+"
        r"((?:2(?:5[0-5]|[0-4]\d)|1\d{2}|[1-9]?\d))\s+"
        r"((?:2(?:5[0-5]|[0-4]\d)|1\d{2}|[1-9]?\d))\s+"
        r"((?:2(?:5[0-5]|[0-4]\d)|1\d{2}|[1-9]?\d))\b"
    )

    @classmethod
    def _normalize_ip_octet_spaces(cls, text: str, log: list) -> str:
        """Convert space-separated IP octets to dotted format.

        "168 153 172 244" → "168.153.172.244"
        "171 110 20 205" → "171.110.20.205"
        "10 0 0 50" → "10.0.0.50"
        """
        original = text
        text = cls._IP_OCTET_SPACE_RE.sub(r"\1.\2.\3.\4", text)
        if text != original:
            log.append({
                "transform": "ip_octet_spaces",
                "description": "Normalized space-separated IP octets to dotted format",
                "changed": True,
            })
        return text

    _IP_OCTET_DOT_RE = re.compile(
        r"\b(\d{1,4})\.(\d{1,4})\.(\d{1,4})\.(\d{1,4})\b"
    )

    @classmethod
    def _normalize_ip_octet_dots(cls, text: str, log: list) -> str:
        """Normalize leading-zero-padded dotted IP octets to standard format.

        "0204.0115.0260.0325" → "204.115.260.325"
        "0103.0207.0142.0216" → "103.207.142.216"

        Strips leading zeros so the CC segment normalizer doesn't
        consume zero-padded IP octets thinking they're CC groups.
        """
        original = text

        def _strip_leading_zeros(m: re.Match) -> str:
            a, b, c, d = m.group(1), m.group(2), m.group(3), m.group(4)
            ia, ib, ic, id_ = int(a), int(b), int(c), int(d)
            # Only strip leading zeros if ALL resulting values are valid
            # IP octets (0-255). This prevents destroying credit card numbers
            # like 5500.0000.0000.0004 where groups > 255 (5500) or leading
            # zeros (0000) that int() would collapse to 0 are legitimate
            # CC groups, not IP octets.
            if all(v <= 255 for v in (ia, ib, ic, id_)):
                return f"{ia}.{ib}.{ic}.{id_}"
            return m.group(0)

        text = cls._IP_OCTET_DOT_RE.sub(_strip_leading_zeros, text)
        if text != original:
            log.append({
                "transform": "ip_octet_dots",
                "description": "Normalized zero-padded IP octets to dotted format",
                "changed": True,
            })
        return text

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

    # ── 14. Hex-decoded SSN ─────────────────────────────────────────

    _HEX_DECODE_RE = re.compile(r"\b([0-9a-fA-F]{18,})\b")

    @classmethod
    def _decode_hex(cls, text: str, log: list) -> str:
        """Detect hex-encoded strings that decode to PII (SSN).

        Long hex strings (18+ hex chars = 9+ bytes) are decoded.
        If the decoded result contains an SSN pattern, replace the
        hex string with the decoded form.

        Low confidence — only fires when decoded content matches SSN pattern.
        """
        original = text

        def _try_decode(m: re.Match[str]) -> str:
            hex_str = m.group(1)
            try:
                raw = bytes.fromhex(hex_str)
                decoded = raw.decode("ascii", errors="replace")
                if _SSN_RECHECK_RE.search(decoded):
                    return decoded
                return m.group(0)
            except (ValueError, UnicodeDecodeError):
                return m.group(0)

        text = cls._HEX_DECODE_RE.sub(_try_decode, text)
        if text != original:
            log.append({
                "transform": "hex_decode",
                "description": "Decoded hex-encoded string containing SSN pattern",
                "changed": True,
            })
        return text

    # ── 15. Base64-decoded SSN ───────────────────────────────────────

    _BASE64_DECODE_RE = re.compile(r"(?<!\w)([A-Za-z0-9+/=]{13,})(?!\w)")

    @classmethod
    def _decode_base64(cls, text: str, log: list) -> str:
        """Detect base64-encoded strings that decode to PII (SSN or EMAIL).

        Base64 strings (length > 12, alphanumeric+/=) are decoded.
        If the decoded result contains an SSN pattern, OR contains an
        email-like pattern (local@domain.tld), replace the base64 text
        with the decoded form.

        Low confidence — only fires when decoded content matches PII patterns.
        """
        original = text

        # Email pattern for decoded content check (no word boundaries since
        # the decoded text may be surrounded by other chars)
        _EMAIL_RECHECK_RE = re.compile(r"[\w.+*-]+@[\w-]+\.[\w.-]+")

        def _try_decode(m: re.Match[str]) -> str:
            b64_str = m.group(1)
            # Skip base64 strings that are explicitly described as encoded/examples
            # (e.g. "Base64 encoded SSN: MTIzLTQ1LTY3ODk=" — these are negative examples,
            # not actual PII that should be decoded)
            start = m.start(1)
            preceding = m.string[max(0, start - 30):start].lower()
            if any(kw in preceding for kw in ["encoded", "base64", "b64", "decodes to"]):
                return m.group(0)
            try:
                raw = base64.b64decode(b64_str)
                decoded = raw.decode("ascii", errors="replace")
                if _SSN_RECHECK_RE.search(decoded) or _EMAIL_RECHECK_RE.search(decoded):
                    return decoded
                return m.group(0)
            except Exception:
                return m.group(0)

        text = cls._BASE64_DECODE_RE.sub(_try_decode, text)
        if text != original:
            log.append({
                "transform": "base64_decode",
                "description": "Decoded base64-encoded string containing SSN pattern",
                "changed": True,
            })
        return text

    # ── 16. Area/Group/Serial spoken SSN ───────────────────────────

    _AREA_SERIAL_RE = re.compile(
        r"\barea\s+(\d+)\s+group\s+(\d+)\s+serial\s+(\d+)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _extract_area_serial(cls, text: str, log: list) -> str:
        """Detect spoken SSN in 'area X group Y serial Z' format.

        'area 150 group 14 serial 1716' → '150-14-1716'

        Low confidence — only fires when the combined numbers look like
        an SSN (3-digit area, 2-digit group, 4-digit serial).
        """
        original = text

        def _combine(m: re.Match[str]) -> str:
            area = m.group(1)
            group = m.group(2)
            serial = m.group(3)
            # SSN format: 3-digit area, 2-digit group, 4-digit serial
            combined = f"{area}-{group}-{serial}"
            if _SSN_RECHECK_RE.search(combined):
                return combined
            return m.group(0)

        text = cls._AREA_SERIAL_RE.sub(_combine, text)
        if text != original:
            log.append({
                "transform": "area_serial",
                "description": "Extracted SSN from 'area X group Y serial Z' format",
                "changed": True,
            })
        return text

    # ── 17. Reconstruct split tokens (concatenation patterns) ──────────────

    # Pattern: quoted strings joined by +
    # e.g. '"john" + "@" + "example" + "." + "com"'
    _CONCAT_RE = re.compile(
        r'(?:"([^"]*)"\s*\+\s*)+"([^"]*)"'
    )

    # Pattern: f-string-like reconstruction
    # e.g. "f'{john}@{example}.{com}'" or "f\"{john}@{example}.{com}\""
    _FSTRING_RE = re.compile(
        r"""f['"](?:[^'"{}]*|\{[^}]*\})+['"]"""
    )

    # Pattern: pipe-separated tokens
    # e.g. 'john | @ | example | . | com' or "john|@|example|.com"
    _PIPE_SEP_RE = re.compile(
        r"(?<!\w)([a-zA-Z0-9._%+\-]+(?:\s*\|\s*[a-zA-Z0-9._%+\-@]+)+)(?!\w)"
    )

    # Pattern: comma-separated quoted tokens
    # e.g. '"john", "@", "example.com"' or "'john', '@', 'example.com'"
    _COMMA_SEP_RE = re.compile(
        r"""(['"])([^'"]+)\1\s*,\s*(?:(['"])([^'"]+)\3(?:\s*,\s*)?)+"""
    )

    @classmethod
    def _reconstruct_split_tokens(cls, text: str, log: list) -> str:
        """Detect and reconstruct PII split across concatenated tokens.

        Handles four patterns:
        1. `"john" + "@" + "example" + "." + "com"` — quoted strings joined by +
        2. `f'{john}@{example}.{com}'` — f-string-like reconstruction
        3. `john | @ | example | . | com` — pipe-separated tokens
        4. `"john", "@", "example.com"` — comma-separated quoted tokens
        """
        original = text

        # 1. Concat pattern: extract all quoted segments joined by +
        def _rebuild_concat(m: re.Match[str]) -> str:
            full = m.group(0)
            # Extract all quoted strings
            parts = re.findall(r'"([^"]*)"', full)
            return "".join(parts)

        text = cls._CONCAT_RE.sub(_rebuild_concat, text)

        # 2. F-string pattern: strip f-string wrapper, concatenate content
        def _rebuild_fstring(m: re.Match[str]) -> str:
            full = m.group(0)
            # Strip f'' or f"" wrapper
            inner = full[1:]  # remove the 'f'
            inner = inner[1:-1]  # remove the outer quotes
            # Replace {var} with the variable name itself, and remove braces
            # e.g. f'{john}@{example}.{com}' → 'john@example.com'
            inner = re.sub(r"\{([^}]*)\}", r"\1", inner)
            return inner

        text = cls._FSTRING_RE.sub(_rebuild_fstring, text)

        # 3. Pipe-separated pattern: strip pipes
        def _rebuild_pipe(m: re.Match[str]) -> str:
            full = m.group(0)
            # Remove pipes and spaces around them
            result = re.sub(r"\s*\|\s*", "", full)
            return result

        text = cls._PIPE_SEP_RE.sub(_rebuild_pipe, text)

        # 4. Comma-separated quoted pattern: concatenate quoted values
        def _rebuild_comma(m: re.Match[str]) -> str:
            full = m.group(0)
            # Extract all quoted strings (single or double)
            parts = re.findall(r"""["']([^"']*)["']""", full)
            return "".join(parts)

        text = cls._COMMA_SEP_RE.sub(_rebuild_comma, text)

        if text != original:
            log.append({
                "transform": "split_tokens",
                "description": "Reconstructed PII split across concatenated/tokenized segments",
                "changed": True,
            })
        return text

    # ═════════════════════════════════════════════════════════════════════
    # NEW TRANSFORMS (A-H) for v3 adversarial dataset
    # ═════════════════════════════════════════════════════════════════════

    # ── A. Hex escape decoder ──────────────────────────────────────────
    # Replace \xHH sequences with their ASCII character
    # e.g. \x34\x35\x31\x32 → "4512"
    _HEX_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{2})")

    @classmethod
    def _decode_hex_escapes(cls, text: str, log: list) -> str:
        """Decode \\xHH hex escape sequences to ASCII characters.

        Runs BEFORE URL percent-decoding. Handles literal \\x34 sequences
        (backslash + 'x' + 2 hex digits) that appear in the text as strings.
        """
        original = text

        def _replace_hex_esc(m: re.Match[str]) -> str:
            cp = int(m.group(1), 16)
            if 0x20 <= cp <= 0x7E:
                return chr(cp)
            return m.group(0)

        text = cls._HEX_ESCAPE_RE.sub(_replace_hex_esc, text)
        if text != original:
            log.append({
                "transform": "hex_escapes",
                "description": "Decoded \\xHH hex escape sequences",
                "changed": True,
            })
        return text

    # ── Percent separator normalizer ──────────────────────────────────
    # After URL decoding, %25→% leaves lone % between word chars.
    # Convert % between word characters to space for COMPANY detection.
    _PCT_BETWEEN_WORDS_RE = re.compile(r"(?<=[a-zA-Z])%(?=[a-zA-Z])")

    @classmethod
    def _normalize_pct_separator(cls, text: str, log: list) -> str:
        """Convert bare '%' between word characters to a space.

        After URL percent-decoding, double-encoded '%25' becomes '%'.
        When '%' sits between two word characters (e.g. Globex%Corporation),
        it was originally a space used in COMPANY names.

        This is a targeted transform — only fires on % between alpha chars.
        """
        original = text
        text = cls._PCT_BETWEEN_WORDS_RE.sub(" ", text)
        if text != original:
            log.append({
                "transform": "pct_separator",
                "description": "Converted % between word characters to space (double-encoding residue)",
                "changed": True,
            })
        return text

    # ── B. Binary 8-bit decoder ────────────────────────────────────────
    # Detect space-separated 8-bit binary groups, strip spaces, decode to ASCII
    # Match 3+ groups (24+ bits = 3+ chars) — catches short binary CC/SSN prefixes
    _BINARY8_RE = re.compile(r"\b[01]{8}(?:\s+[01]{8}){3,}\b")

    @classmethod
    def _decode_binary_strings(cls, text: str, log: list) -> str:
        """Detect binary (0/1) strings, decode 8-bit chunks to ASCII.

        Handles space-separated 8-bit groups (3+ groups = 24+ bits).
        Only replaces when the decoded result contains PII-relevant characters.
        After decoding, extracts embedded digit-only runs (CC/SSN/phone numbers)
        that may be mixed with prefix words in the decoded text.
        """
        original = text

        def _try_decode_binary(m: re.Match[str]) -> str:
            bin_str = m.group(0)
            cleaned = bin_str.replace(" ", "")
            if len(cleaned) % 8 != 0:
                return bin_str
            chars = []
            for i in range(0, len(cleaned), 8):
                byte = cleaned[i:i+8]
                chars.append(chr(int(byte, 2)))
            decoded = "".join(chars)
            # Only replace if decoded has PII-relevant chars
            if any(c.isalnum() or c in "@._-:# " for c in decoded):
                # Split digit suffix from alpha prefix so standalone digit
                # patterns (CC, SSN, phone) can match independently.
                # E.g. "TEST-CARD12345670123" — separate the digit run from
                # the alphabetic prefix so the CC/phone patterns can match
                # just the digits.
                separated = re.sub(
                    r"([a-zA-Z-]+)(\d{8,})$",
                    r"\1 \2",
                    decoded,
                )
                return separated
            return bin_str

        text = cls._BINARY8_RE.sub(_try_decode_binary, text)
        if text != original:
            log.append({
                "transform": "binary_strings",
                "description": "Decoded binary (8-bit) encoded strings",
                "changed": True,
            })
        return text

    # ── C. Unicode fractions → decimals ────────────────────────────────
    _UNICODE_FRACTION_MAP = {
        "\u00BD": "0.5",     # ½ → 0.5
        "\u2153": "0.333",   # ⅓ → 0.333
        "\u2154": "0.667",   # ⅔ → 0.667
        "\u00BC": "0.25",   # ¼ → 0.25
        "\u00BE": "0.75",   # ¾ → 0.75
        "\u2155": "0.2",    # ⅕ → 0.2
        "\u2156": "0.4",    # ⅖ → 0.4
        "\u2157": "0.6",    # ⅗ → 0.6
        "\u2158": "0.8",    # ⅘ → 0.8
        "\u2159": "0.167",  # ⅙ → 0.167
        "\u215A": "0.833",  # ⅚ → 0.833
        "\u215B": "0.125",  # ⅛ → 0.125
        "\u215C": "0.375",  # ⅜ → 0.375
        "\u215D": "0.625",  # ⅝ → 0.625
        "\u215E": "0.875",  # ⅞ → 0.875
    }
    _UNICODE_FRACTION_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_FRACTION_MAP))

    @classmethod
    def _normalize_unicode_fractions(cls, text: str, log: list) -> str:
        """Convert Unicode fraction characters to decimal strings.

        e.g. ½ → 0.5, ⅘ → 0.8, ¾ → 0.75
        This allows subsequent phone/date/SSN patterns to match.
        """
        original = text
        text = cls._UNICODE_FRACTION_RE.sub(
            lambda m: cls._UNICODE_FRACTION_MAP[m.group(0)],
            text,
        )
        if text != original:
            log.append({
                "transform": "unicode_fractions",
                "description": "Normalized Unicode fraction characters to decimal values",
                "changed": True,
            })
        return text

    # ── D. Extended l33tspeak decoder ───────────────────────────────────
    _L33T_MAP = str.maketrans({
        "0": "o", "3": "e", "1": "l", "4": "a", "5": "s",
        "7": "t", "8": "b", "@": "a", "$": "s",
    })
    # Match word-like tokens that could contain l33t
    _L33T_PII_TOKEN_RE = re.compile(
        r"\b(?:[a-zA-Z][a-zA-Z0-9_@$]{3,}|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    )
    # Match tokens with mixed case + numerals (classic l33t indicator)
    _L33T_MIXED_TOKEN_RE = re.compile(
        r"(?<!\w)(?:[a-z]+\d+[a-z]+\d*[a-z]*|[a-z]*\d+[a-z]+\d+[a-z]*|[A-Z]\d[A-Z][a-z]*\d|[A-Z][a-z]*\d[A-Z][a-z]*)\w{2,}(?!\w)",
        re.IGNORECASE,
    )

    @classmethod
    def _decode_l33t(cls, text: str, log: list) -> str:
        """Decode extended l33tspeak substitutions in PII-adjacent tokens.

        Only applied when the token looks like it could be PII (word with
        embedded numerals or email-like). Handles patterns like 4dm1n→admin.
        """
        original = text

        def _try_l33t(m: re.Match[str]) -> str:
            token = m.group(0)
            # Skip tokens where >50% of characters are digits — these are
            # numeric codes (passport numbers, IBANs, etc.), not l33tspeak.
            digit_ratio = sum(1 for c in token if c.isdigit()) / max(len(token), 1)
            if digit_ratio > 0.5:
                return token
            decoded = token.translate(cls._L33T_MAP)
            if decoded != token:
                orig_digits = sum(1 for c in token if c.isdigit())
                new_digits = sum(1 for c in decoded if c.isdigit())
                if new_digits < orig_digits or "@" in decoded:
                    return decoded
            return token

        text = cls._L33T_PII_TOKEN_RE.sub(_try_l33t, text)
        text = cls._L33T_MIXED_TOKEN_RE.sub(_try_l33t, text)
        if text != original:
            log.append({
                "transform": "l33t_decode",
                "description": "Decoded extended l33tspeak patterns in PII tokens",
                "changed": True,
            })
        return text

    # ── E. Morse code decoder ──────────────────────────────────────────
    _MORSE_TABLE = {
        ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E",
        "..-.": "F", "--.": "G", "....": "H", "..": "I", ".---": "J",
        "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
        ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T",
        "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y",
        "--..": "Z",
        "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4",
        ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9",
        ".-.-.-": ".",  # period
        "--..--": ",",  # comma
        "..--..": "?",  # question mark
        ".----.": "'",  # apostrophe
        "-.-.--": "!",  # exclamation mark
        "-..-.": "/",   # slash
        "-.--.": "(",   # left paren
        "-.--.-": ")",  # right paren
        ".-...": "&",   # ampersand
        "---...": ":",  # colon
        "-.-.-.": ";",  # semicolon
        "-...-": "=",   # equals
        ".-.-.": "+",   # plus
        ".-..-.": "\"", # double quote
        "..--.-": "_",  # underscore
        "...-..-": "$",  # dollar sign
        ".--.-.": "@",   # at sign
    }
    _MORSE_RE = re.compile(
        r"(?<!\w)([.\-]+(?:\s+[.\-]+)+)(?!\w)"
    )

    @classmethod
    def _decode_morse(cls, text: str, log: list) -> str:
        """Detect Morse code sequences and decode them to ASCII.

        Handles standard International Morse code for A-Z, 0-9, and common
        punctuation. Only replaces when decoded result looks like PII.
        """
        original = text

        def _try_morse(m: re.Match[str]) -> str:
            morse_str = m.group(1)
            codes = morse_str.split()
            decoded_chars = []
            for code in codes:
                ch = cls._MORSE_TABLE.get(code)
                if ch is None:
                    return m.group(0)
                decoded_chars.append(ch)
            decoded = "".join(decoded_chars)
            if decoded and any(c.isalnum() or c in "@.:/-_" for c in decoded):
                return decoded
            return m.group(0)

        text = cls._MORSE_RE.sub(_try_morse, text)
        if text != original:
            log.append({
                "transform": "morse_decode",
                "description": "Decoded Morse code sequences",
                "changed": True,
            })
        return text

    # ── F. XML numeric escape decoder ───────────────────────────────────
    # Run BEFORE existing HTML entity decoder
    _XML_DECIMAL_RE = re.compile(r"&#(\d{1,5});")
    _XML_HEX_RE = re.compile(r"&#[xX]([0-9a-fA-F]{1,4});")

    @classmethod
    def _decode_xml_escape(cls, text: str, log: list) -> str:
        """Decode XML numeric character references (&#DDD; and &#xHH;).

        Runs BEFORE the existing HTML entity decoder so that &#49; etc.
        get decoded to digit characters before the standard entity pass
        handles named entities like &lt; and &amp;.
        """
        original = text

        def _replace_decimal(m: re.Match[str]) -> str:
            cp = int(m.group(1))
            if 0x20 <= cp <= 0x7E or 0xA0 <= cp <= 0xFF:
                return chr(cp)
            return m.group(0)

        def _replace_hex(m: re.Match[str]) -> str:
            cp = int(m.group(1), 16)
            if 0x20 <= cp <= 0x7E or 0xA0 <= cp <= 0xFF:
                return chr(cp)
            return m.group(0)

        text = cls._XML_DECIMAL_RE.sub(_replace_decimal, text)
        text = cls._XML_HEX_RE.sub(_replace_hex, text)
        if text != original:
            log.append({
                "transform": "xml_escape",
                "description": "Decoded XML numeric character references",
                "changed": True,
            })
        return text

    # ── G. Punctuation-stuffing remover ─────────────────────────────────
    # Detect runs where every 2nd character is non-alphanumeric (punctuation)
    _PUNCT_STUFF_LONG_RE = re.compile(
        r"(?<!\w)((?:[a-zA-Z0-9][^\w\s]){6,}[a-zA-Z0-9])(?!\w)"
    )

    @classmethod
    def _remove_punctuation_stuffing(cls, text: str, log: list) -> str:
        """Remove interleaved punctuation from runs where punctuation
        is inserted between every digit/letter.

        e.g. "1..9..8..5..--..0..4..--..1..5" → "1985--04--15" → after date normalizer → "1985-04-15"
        e.g. "O..p,,e;;r..a,,t;;i..o,,n;;" → "Operation"
        """
        original = text

        def _clean_stuffed(m: re.Match[str]) -> str:
            full = m.group(0)
            # Remove all non-alphanumeric, non-whitespace characters
            cleaned = re.sub(r"[^\w\s]", "", full)
            return cleaned

        text = cls._PUNCT_STUFF_LONG_RE.sub(_clean_stuffed, text)
        if text != original:
            log.append({
                "transform": "punct_stuffing",
                "description": "Removed punctuation stuffing from obfuscated text",
                "changed": True,
            })
        return text

    # ── H. Pig latin decoder ────────────────────────────────────────────
    # Detect words ending with "ay" suffix (pig latin pattern)
    _PIG_LATIN_RE = re.compile(r"\b([a-zA-Z]+)ay\b", re.IGNORECASE)

    @classmethod
    def _decode_pig_latin(cls, text: str, log: list) -> str:
        """Detect and decode pig-latin obfuscated words.

        Standard pig latin: take leading consonant(s) to end + "ay"
        e.g. "world" → "orldway", "Mexico" → "exicoMay", "hello" → "ellohay"

        Reverse: strip "ay", move trailing consonant cluster to front.
        e.g. "orldway" → "world", "exicoMay" → "Mexico", "ellohay" → "hello"
        """
        original = text

        def _try_decode_pig(m: re.Match[str]) -> str:
            word = m.group(1)

            # Pattern for capitalized pig latin (e.g. "exicoMay", "orldHay")
            # Find uppercase letters in otherwise lowercase word
            upper_positions = [i for i, c in enumerate(word) if c.isupper()]
            if upper_positions:
                # The consonant cluster moved to end starts at the first uppercase letter
                first_upper = upper_positions[0]
                # The part from first_upper onward is the original leading consonants
                prefix = word[first_upper:]  # e.g. "M" from "exicoMay"
                root = word[:first_upper]     # e.g. "exico" from "exicoMay"
                result = prefix + root
                if result:
                    result = result[0].upper() + result[1:].lower()
                return result

            # Pattern for all-lowercase pig latin (e.g. "orldway")
            # Standard reverse: find trailing consonant cluster after last vowel
            # e.g. "orldway": vowel sequence ends at 'a', trailing consonants "w"
            trailing_match = re.search(r"[aeiou].*?([^aeiou]+)$", word, re.IGNORECASE)
            if trailing_match:
                trailing = trailing_match.group(1)
                rest = word[:-len(trailing)]
                result = trailing + rest
                return result

            return m.group(0)

        text = cls._PIG_LATIN_RE.sub(_try_decode_pig, text)
        if text != original:
            log.append({
                "transform": "pig_latin",
                "description": "Decoded pig-latin style obfuscation",
                "changed": True,
            })
        return text

    # ── I. Case-shift swap ────────────────────────────────────────────
    # Reverse the case of every ASCII letter (upper→lower, lower→upper)
    # Catches "case-shifted" obfuscation like nEW yORK → New York

    @classmethod
    def _swap_case(cls, text: str, log: list) -> str:
        """Swap the case of every ASCII letter in the text.

        Reverse case-shift obfuscation: letters that had their case flipped
        are restored. E.g. 'nEW yORK' → 'New York', 'hOUSTON' → 'Houston'.

        Only applied when a word-level analysis suggests case-shifting
        is present (at least one word with ≥3 letters where ≥70% of letters
        are the 'wrong' case relative to natural English capitalization).
        """
        original = text

        def _is_case_shifted(word: str) -> bool:
            """Heuristic: a word is case-shifted if ≥70% of its letters
            are in the 'unnatural' case for its position.

            For a word starting with lowercase when it should be capitalized
            (e.g. 'nEW' — first letter lower, rest upper), or starting with
            uppercase when surrounded by lowercase in the rest.
            """
            letters = [c for c in word if c.isalpha()]
            if len(letters) < 3:
                return False

            # Count upper and lower among letters
            upper = sum(1 for c in letters if c.isupper())
            lower = sum(1 for c in letters if c.islower())

            # Case-shifted: the 'unnatural' case dominates
            # Natural: first letter capital, rest lowercase (or all same case)
            # Case-shifted: first letter lowercase when it could be capital
            #   e.g. nEW → 1 lower, 2 upper → upper dominates = case-shifted
            #   e.g. hOUSTON → 1 lower, 6 upper → upper dominates = case-shifted
            # Also: 'pHOENIX' → 1 upper, 5 lower with first=lower → mid-word capital = case-shifted

            # Check if the majority case is opposite to the first letter's case
            # For a word starting lower: if upper > lower, it's case-shifted
            first = word[0]
            if first.islower() and upper >= 2 and upper >= lower:
                return True
            # For a word starting upper: if upper < lower it's shifted
            if first.isupper() and lower >= 2 and lower > upper:
                return True
            # Word with all letters the 'wrong' case: all upper or all lower
            if upper == len(letters) and first.isupper():
                # All caps starting with capital — this is normal shouting, not case-shifted
                return False
            if lower == len(letters) and first.islower():
                # All lowercase — this is normal lowercase, not case-shifted
                return False

            return False

        # Split into words, check each
        words = text.split()
        changed = False
        new_words = []
        for word in words:
            if _is_case_shifted(word):
                new_words.append(word.swapcase())
                changed = True
            else:
                new_words.append(word)

        if changed:
            text = " ".join(new_words)
            log.append({
                "transform": "swap_case",
                "description": "Swapped case on case-shifted words (nEW→New, hOUSTON→Houston)",
                "changed": True,
            })
        return text

    # ── J. Reverse-words decoder ──────────────────────────────────────────
    # Detect email-like constructs with reversed domain segments and reversed
    # local-part words (e.g., "gro.moc@olleh" → "hello@com.org").
    #
    # NOTE: Reversed-name decoding (e.g. "Doe Jane" → "Jane Doe") is DISABLED
    # because the simple regex ``\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b`` matched
    # ANY two capitalized words — including correctly-ordered names like "Jane
    # Smith" — and reversed them, destroying all PERSON / CUSTOMER_NAME /
    # EMPLOYEE_NAME pattern detection. This caused 7+5 label collisions,
    # zeroing recall on CUSTOMER_NAME and EMPLOYEE_NAME.

    _REVERSED_EMAIL_RE = re.compile(
            r"(?<!\w)([a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)+)@([a-zA-Z0-9_]+(?:_[a-zA-Z0-9_]+)+)(?!\w)"
    )

    @classmethod
    def _decode_reversed_words(cls, text: str, log: list) -> str:
            """Detect and decode reversed-word obfuscation patterns.

            Only handles reversed-email patterns (domain segments reversed).
            Reversed-name decoding is DISABLED — see module docstring.

            Only fires when the reversal produces a detectable improvement
            (email-like pattern for emails).
            """
            original = text

            # ── Pattern 1: Reversed email ──
            def _reverse_email(m: re.Match[str]) -> str:
                domain_part = m.group(1)   # e.g. "gro.moc"
                local_part = m.group(2)    # e.g. "olleh_321_ydob_emosewa"

                # Reverse domain: split by '.', reverse order
                domain_segments = domain_part.split(".")
                domain_segments.reverse()
                recovered_domain = ".".join(domain_segments)

                # Reverse local part: split by '_', reverse order, reverse each word
                words = local_part.split("_")
                words.reverse()
                recovered_words = [w[::-1] for w in words]
                recovered_local = "_".join(recovered_words)

                return f"{recovered_local}@{recovered_domain}"

            text = cls._REVERSED_EMAIL_RE.sub(_reverse_email, text)

            if text != original:
                log.append({
                    "transform": "reversed_words",
                    "description": "Decoded reversed-word obfuscation (email segments only)",
                    "changed": True,
                })
            return text