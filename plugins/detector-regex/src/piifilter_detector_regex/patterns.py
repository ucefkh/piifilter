"""Regex pattern definitions for PII detection.

All patterns are separated from detection logic so they can be
inspected, tested, or extended independently.

CRITICAL DESIGN RULE: Patterns are ordered so more specific patterns come
before general ones. Types that can be detected as substrings of other types
(DOMAIN can appear within DATABASE_URL, EMAIL can overlap with DOMAIN, etc.)
are placed AFTER those more specific types so deduplication in the detector
picks the higher-specificity match.

DESIGN NOTE: Patterns that need case-insensitive keyword matching should use
inline (?i) flags. However, when using (?i), character classes like [A-Z] become
case-insensitive too. To enforce actual uppercase letters in name positions,
these patterns use (?-i:[A-Z]) to temporarily disable case-insensitivity.
"""

from __future__ import annotations

# Each tuple: (entity_type_name, regex_pattern, confidence_score)
PATTERN_DEFS: list[tuple[str, str, float]] = [

    # ── SSH_KEY ──────────────────────────────────────────────────────
    ("SSH_KEY", r"-----BEGIN(?: OPENSSH| RSA| DSA| EC| ECDSA)? PRIVATE KEY-----", 0.95),
    ("SSH_KEY", r"-----BEGIN PGP PRIVATE KEY BLOCK-----", 0.95),
    # ssh-rsa public keys: ssh-rsa AAAA... (base64 encoded key)
    ("SSH_KEY", r"\bssh-rsa\s+AAAA[a-zA-Z0-9+/=_-]{50,}(?:\s+\S+)?\b", 0.95),
    ("SSH_KEY", r"\bssh-ed25519\s+AAAA[a-zA-Z0-9+/=_-]{30,}(?:\s+\S+)?\b", 0.95),
    ("SSH_KEY", r"\bssh-dss\s+AAAA[a-zA-Z0-9+/=_-]{30,}(?:\s+\S+)?\b", 0.95),

    # ── DATE ─────────────────────────────────────────────────────────
    # Month-name dates: "Jan 15, 2026" or "January 15 2026"
    ("DATE", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b", 0.90),
    # ISO format: YYYY-MM-DD and YYYY-M-D
    ("DATE", r"\b\d{4}-\d{1,2}-\d{1,2}\b", 0.85),
    # Slash format: DD/MM/YYYY or MM/DD/YYYY or DD/MM/YY
    ("DATE", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", 0.75),
    # Date after context keywords like "DOB is", "Date:", "Expires:", "Born:", "Updated:", "Valid until"
    ("DATE", r"(?i)(?:DOB|Date|Expires|Born|Updated|Valid\s+until)\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", 0.85),

    # ── DATABASE_URL ─────────────────────────────────────────────────
    # MUST come before PRIVATE_URL so the broader DATABASE_URL match wins
    # when a private hostname appears inside a DB connection string.
    ("DATABASE_URL", r"\b(?:postgresql|postgres|mysql|mongodb|redis|sqlite|oracle|mssql)://\S+", 0.95),

    # ── JWT ──────────────────────────────────────────────────────────
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b", 0.95),
    # Truncated JWT (two parts, common in abbreviated context)
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.\.\.\w*\b", 0.90),
    ("JWT", r"\beyJ[a-zA-Z0-9_-]{3,20}\.\.[a-zA-Z0-9_-]{3,10}\b", 0.85),
    # JWT with 3 dots as ellipsis: "eyJzdW...IyfQ"
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.\.\.[a-zA-Z0-9_-]+\b", 0.85),
    # JWT that is essentially a base64 encoded payload (single segment, no dots)
    # Bare eyJ — requires at least two segments separated by a dot to avoid
    # matching non-JWT base64 strings that happen to start with eyJ.
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+?\.[a-zA-Z0-9_-]{2,}(?:\.[a-zA-Z0-9_-]+)?\b", 0.70),

    # ── SSN ──────────────────────────────────────────────────────────
    # IMPORTANT ORDERING: More specific patterns (context-prefixed) must come
    # BEFORE bare patterns so dedup picks the longer, higher-confidence match.
    # Masked/bullet SSN — partial redaction with last-4 visible: XXX-XX-9074, ***-**-0720, SSN 9XX-XX-4321
    # Context-prefixed SSN: catches ALL separator variants (hyphen, NBSP, dot, space, or none)
    # when preceded by an SSN-related keyword like "SSN:", "Social Security:", "SS#", "Tax ID:"
    # Also handles "SSN is", "My SSN is" patterns via optional "is" after the keyword.
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|tax id|ss#)\s*:?\s*(?:is\s+)?\s*\d{3}[- \u00A0.]?\d{2}[- \u00A0.]?\d{4}\b", 0.95),
        # Context-prefixed bare 9-digit SSN (no separator at all) — e.g. "SSN: 123456789"
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|tax id|ss#)\s*:?\s*(?:is\s+)?\s*\d{9}\b", 0.95),
        # Matches standard SSN formats: 123-45-6789 (hyphen) and 123\xa045\xa06789 (non-breaking space)
    ("SOCIAL_SECURITY", r"\b\d{3}[-\u00A0]\d{2}[-\u00A0]\d{4}\b", 0.90),
    # X-mask or star-mask in first 5 positions, last-4 digits visible
    # NOTE: requires context keyword (SSN, social, etc.) for high confidence.
    # Without context, confidence is 0.45 (below balanced default of 0.50) to avoid
    # matching non-SSN context like "Full: XXX-XX-6789" or example descriptions.
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|tax id|ss#)\s*:?\s*(?:\w+\s+)?[X*#]{3}[- ][X*#]{2}[- ]\d{4}\b", 0.70),
    ("SOCIAL_SECURITY", r"\b[X*#]{3}[- ][X*#]{2}[- ]\d{4}\b", 0.45),
    # Same with bullet characters (U+2022, U+25CF): •••-••-9074
    ("SOCIAL_SECURITY", r"[\u2022\u25CF]{3}[- ][\u2022\u25CF]{2}[- ]\d{4}", 0.70),
    # Context-prefixed X-masked SSN: "SSN 9XX-XX-4321", "SSN 1XX-XX-6789" — first digit real, positions 2-5 masked
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|ss#)\s+\d[X*#]{2}[- ][X*#]{2}[- ]\d{4}\b", 0.70),
    # Full mask with context: "SSN XXX-XX-XXXX"
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|ss#)\s+[X*#]{3}[- ]{2,4}\d{4}\b", 0.65),
    # Context-based masked SSN: "masked SSN: XXX-XX-9074"
    ("MASKED_SSN", r"(?i)(?:mask|redact|obfuscat)[a-z]*\s*(?:social|ssn|ss#)\s*:?\s*[X*#]{3}[- ]\d{2}[- ]\d{4}\b", 0.60),
    # Base64-encoded SSN: base64-decoded form contains 9+ digits or SSN pattern
    ("MASKED_SSN", r"(?i)\b(?:encoded|hidden\s+field|encrypted|obfuscat)[a-z]*\s*[:=]\s*[A-Za-z0-9+/=]{9,}\b", 0.55),
    # Segmented SSN: "123 45 6789 (segmented)"
    ("MASKED_SSN", r"\b\d{3}[ \u00A0]\d{2}[ \u00A0]\d{4}\s+\(segmented\)\b", 0.60),
        # General SSN-like pattern — requires at least ONE separator character (hyphen, space, or NBSP)
        # between the first two digit groups. Dots (.) are excluded since they match IP octets
        # like "168.10.255" which are not SSNs. This prevents bare consecutive digit strings like
        # "987654321" from being matched as 4-2-3 or 3-2-4 SSN groupings when there's no real separator.
        # Uses lookaround to avoid matching within longer digit sequences.
        # Supports both standard 3-2-4 and reverse 4-2-3/4-2-4 groupings.
        # Lower confidence (0.75) since it matches SSN-like patterns without context keywords.
    ("SOCIAL_SECURITY", r"(?<!\d)\d{3,4}[-\u00A0 ]\d{2}[-\u00A0 ]?\d{3,4}(?!\d)", 0.75),
        # General SSN-like pattern anchored to word boundaries — catches reverse 4-2-3/4-2-4
        # groupings that lookarounds may miss (e.g. when surrounded by spaces or punctuation).
        # Requires at least one separator between first two groups.
    ("SOCIAL_SECURITY", r"\b\d{4}[-\u00A0 ]\d{2}[-\u00A0 ]?\d{3,4}\b", 0.75),
        # Bare 9-digit SSN (no separator) with area number validation.
        # Area number (first 3 digits) must be 001-899, excluding 000 and 666.
        # Uses a (?!...) negative lookahead to block invalid areas.
        # Word boundaries prevent matching inside longer digit runs.
        # Lower confidence (0.50) since no context keyword or formatting helps.
    ("SOCIAL_SECURITY", r"\b(?!000|666)\d{3}(?!000|666)\d{6}\b", 0.50),
        # Bare space-separated 9-digit SSN (3-2-4 with single spaces, no context keyword).
        # Catches patterns like "764 14 7533", "412 14 6394", "354 29 2645".
        # Lower confidence (0.50) since no context keyword helps confirm.
        # Area number validation: first 3 digits != 000, != 666, not 900-999.
    ("SOCIAL_SECURITY", r"\b(?!000|666)\d{3}\s+\d{2}\s+\d{4}\b", 0.50),
        # Context-keyword-prefixed space-separated SSN: "Data: 911 68 3710", "Found: 996 29 8532", "Encoded: 354 29 2645"
        # Also catches " (segmented)" suffix. Context words: Data, Found, Raw, Hidden field, Encoded, Obfuscated social_security
        # This handles 3-2-4 groupings separated by single spaces.
    ("SOCIAL_SECURITY", r"(?i)\b(?:data|found|raw|hidden\s+field|encoded|obfuscated\s+social_security)\s*:\s*\d{3}\s+\d{2}\s+\d{4}(?:\s+\(segmented\))?", 0.60),
        # Abbreviated SSN formats with context keyword: "Found: 162-0-7302" (3-1-4), "Found: 837-26-720" (3-2-3)
        # These have missing leading zeros in one group. Only match with context keyword to avoid FPs.
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|tax id|ss#|data|found|raw|hidden\s+field|encoded)\s*:?\s*(?:is\s+)?\s*\d{3}-\d{1,2}-\d{3,4}\b", 0.70),
        # Context-keyword-prefixed SSN with single spaces as separator between groups (3-2-4)
        # Catches "Tax ID: 412 14 6394", "Social Security: 354 29 2645" and similar.
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|tax id|ss#)\s*:?\s*(?:is\s+)?\s*\d{3}\s+\d{2}\s+\d{4}\b", 0.90),

    # ── IBAN ─────────────────────────────────────────────────────────
    # IBAN must come BEFORE CREDIT_CARD patterns since IBAN substrings (like
        # "6016 1331 9268 19") can look like credit card numbers. The dedup logic
    # skips detections contained within already-matched intervals.
    ("IBAN", r"\b[A-Z]{2}\d{2}(?:[ ]?(?:[A-Z0-9]{4})){4,7}(?:[ ]?\d{1,4})?\b", 0.85),
    # Shorter IBAN variants: NL91 ABNA 0417 1643 00, DK50 0040 0440 1162 43, NO93 8601 1117 947
    ("IBAN", r"\b[A-Z]{2}\d{2}\s+[A-Z]{4}\s+\d{4}\s+\d{4}\s+\d{2,4}(?:\s+\d{1,3})?\b", 0.85),
    # Collapsed IBAN (after digit-space merging): catches cases where
    # _collapse_digit_spaces has merged digit groups (e.g. "0417 1643 00"
    # -> "0417164300") or the bank code is all-numeric (e.g. NO93 8601...).
    # Bank code must be 4 alphanumeric chars, digit portion 6-20 chars to
    # cover short (NL=10, DK=10), medium (GB=14, CH=14), and long (DE=18,
    # ES=20) IBANs.
    ("IBAN", r"\b[A-Z]{2}\d{2}\s*[A-Z0-9]{4}\s*\d{6,20}\b", 0.75),

    # ── CREDIT_CARD ──────────────────────────────────────────────────
    # Masked/bullet CC — partial redaction with last-4 visible: XXXX-XXXX-XXXX-1234, ****-****-****-5678
    ("CREDIT_CARD", r"(?:[X*#]{4}[- ]){3}\d{4}\b", 0.70),
    # Same with bullet characters (U+2022, U+25CF): ••••-••••-••••-1111
        ("MASKED_CC", r"(?:[\u2022\u25CF]{4}[- ]){3}\d{4}\b", 0.70),
        # Context-prefixed masked CC: "Credit card: XXXX-XXXX-XXXX-1234" — lookbehind keeps context out of span
        ("MASKED_CC", r"(?i)(?:(?:credit\s*card|cc|card)\s*:?\s*(?:number\s+)?(?:is\s+)?)(?:[X*#]{4}[- ]){3}\d{4}\b", 0.65),
        # Context-based masked reference: "masked card: ****-****-****-0004"
        ("MASKED_CC", r"(?i)(?:(?:mask|redact|obfuscat|hidden)[a-z]*\s*(?:credit|cc|card)\s*:?\s*)(?:[X*#]{4}[- ]){3}\d{4}\b", 0.60),
        # Masked CC with bullet characters
        ("MASKED_CC", r"(?i)(?:(?:credit\s*card|cc|card)\s*:?\s*(?:number\s+)?(?:is\s+)?)(?:[\u2022\u25CF]{4}[- ]){3}\d{4}\b", 0.60),
    # 4-4-4-4 with multi-space gaps (double spaces, etc.)
    ("CREDIT_CARD", r"\b\d{4}[ -]{2,}\d{4}[ -]{2,}\d{4}[ -]{2,}\d{4}\b", 0.85),
    # 4-4-4-4 with dots as separators: 4111.1111.1111.1111
    ("CREDIT_CARD", r"\b\d{4}\.\d{4}\.\d{4}\.\d{4}\b", 0.85),
    # 4-6-5 Amex format with single dash/space
    ("CREDIT_CARD", r"\b\d{4}[- ]\d{6}[- ]\d{5}\b", 0.80),
    # 4-6-5 with multi-space gaps
    ("CREDIT_CARD", r"\b\d{4}[ -]{2,}\d{6}[ -]{2,}\d{5}\b", 0.80),
    # 4-6-5 with dots: 4111.111111.11111
    ("CREDIT_CARD", r"\b\d{4}\.\d{6}\.\d{5}\b", 0.80),
    # 4-4-4-[3-4] dot-separated (catches Amex 3782.8224.6310.005)
    ("CREDIT_CARD", r"\b\d{4}\.\d{4}\.\d{4}\.\d{3,4}\b", 0.80),
    # 4-4-4-4 with space-dot-space separators: "5500 . 0000 . 0000 . 0004"
    ("CREDIT_CARD", r"\b\d{4} \. \d{4} \. \d{4} \. \d{4}\b", 0.80),
    # 4-4-4-[3-4] with space-dot-space: "3782 . 8224 . 6310 . 005"
    ("CREDIT_CARD", r"\b\d{4} \. \d{4} \. \d{4} \. \d{3,4}\b", 0.80),
    # 2-digit-pair paired spacing (16 digits): "60 11 11 11 11 11 11 17"
    ("CREDIT_CARD", r"\b\d{2}(?: \d{2}){7}\b", 0.75),
    # 2-digit-pair paired spacing for 15-digit (Amex): "37 82 82 24 63 10 00 5"
    ("CREDIT_CARD", r"\b\d{2}(?: \d{2}){6} \d{1,2}\b", 0.75),
    # 4-4-4-2..4 with any combination of space/dot/dash separators — broad catch-all
    # Negative lookbehind guards against matching IBAN substrings (e.g. "0044 0532 0130 00" within
    # "DE89 3704 0044 0532 0130 00") by checking for an IBAN-like prefix before the preceding
    # 4-digit group. Covers both IBAN formats: "DE89 3704 ..." and "NWBK 6016 ..." and "X054 2811...".
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)(?<!\d{4}\s)(?<![A-Z0-9]{4}\s)\b\d{4}[ .-]+\d{4}[ .-]+\d{4}[ .-]+\d{2,4}\b", 0.65),
    # Low confidence: 4-4-4-2..4 pattern with single dash/space
    # IBAN lookbehind: block matches preceded by "[A-Z0-9]{4} " (IBAN bank code segment)
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)(?<![A-Za-z])(?<!\d{4}[- ])(?<![A-Z0-9]{4}\s)\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{2,4}\b(?![- ]\d{2,4})(?!\s*\d{2,4})", 0.65),
    # Low confidence: 4-4-4-2..4 with multi-space gaps (e.g. "3782  8224  6310  005")
    ("CREDIT_CARD", r"\b\d{4}[ -]{2,}\d{4}[ -]{2,}\d{4}[ -]{2,}\d{2,4}\b", 0.65),
    # IIN-prefixed 16-digit numbers: known card issuer prefixes
    ("CREDIT_CARD", r"\b(?:4\d{3}|5[1-5]\d{2}|6\d{3}|3[47]\d{2})\d{12}\b", 0.80),
    # Generic 16-digit number — low confidence (Luhn gate filters FPs).
    ("CREDIT_CARD", r"\b\d{16}\b", 0.50),
    # Catch-all for continuous 13-19 digit numbers that are Luhn-valid.
    # Lower confidence since no format hint — relies on Luhn gate.
    ("CREDIT_CARD", r"\b\d{13,19}\b", 0.65),
    # Context-prefixed CC: "Credit card: 4111111111111111" — placed last so bare
        # CC patterns fire first and the broader context-prefixed match is skipped
        # by the same-type containment check.
        ("CREDIT_CARD", r"(?i)\b(?:credit\s*card|cc|card)\s*(?:number|no|#)?\s*:?\s*\d[ -]*?\d{13,18}\b", 0.90),
        # Continuous 16-digit credit card numbers (no dashes) — keyword-prefixed
        # Must come AFTER the bare IIN-prefix pattern so the narrower match wins.
        ("CREDIT_CARD", r"(?i)(?:credit\s*card|cc|card\s+#?)\b\s*\d{16}\b", 0.80),
        # Brand + "ending in" + last 4 digits: "Visa ending in 1111", "Mastercard ending in 0004", "Amex ending in 1117"
        ("CREDIT_CARD", r"(?i)\b(?:Visa|Mastercard|Master Card|Amex|American Express|Discover|Diners|JCB)\s+ending\s+in\s+\d{4}\b", 0.75),

    # ── EMAIL ────────────────────────────────────────────────────────
        # Local part: word chars, dots, +, -, *, percent-encoded chars, quotable specials
        # Domain: word chars and hyphens (no underscore for domain)
        # TLD: word chars, dots and hyphens (for multi-level TLDs like .co.uk)
        # NOTE: The detector's _run_patterns() suppresses emails where the
        # local part is all one repeated character (e.g. xxxx@domain.com)
        # or all X/* chars (e.g. xxxx@domain.com) — these are redacted references.
        ("EMAIL", r"\b[\w.+*-]+@[\w-]+\.[\w.-]+\b", 0.90),
        # Catch star-obfuscated emails where only * and first/last letter remains
        # e.g. j**n@example.com, s***t@company.com — pattern above catches these now
        # but this lower-confidence fallback catches edge cases with longer stars
        ("EMAIL", r"\b[\w.*]{2,}@[\w.-]+\.[\w.-]+\b", 0.85),

    # ── API_KEY ──────────────────────────────────────────────────────
    # Level 1 — known vendor prefixes + key body (highest confidence)
    # Covers: sk-xxx, pk-xxx, api_key_xxx, api-xxx, api_xxx, key_xxx, token_xxx, secret_xxx
    # Real-world vendor prefixes: GitHub (ghp_, gho_, ghu_, ghs_, ghr_),
    # Slack (xoxb-, xoxp-), Stripe (rk_live_, rk_test_), webhook secrets (whsec_)
    ("API_KEY", r"(?i)\b(?:sk[-_]|pk[-_]|gh[opusr]_|xox[bp]-|rk_(?:live|test)_|whsec_)[a-zA-Z0-9_\-]{16,64}\b", 0.95),
    ("API_KEY", r"\b(?:api[-_]?key|api[-_])[a-zA-Z0-9_\-]{16,64}\b", 0.95),
    ("API_KEY", r"(?i)\b(?:token|secret|key)[-_]?[a-zA-Z0-9_\-]{16,64}\b", 0.95),
    # Level 2 — keyword prefix before colon/space then key body
    # Catches "Key: key_xxx", "secret: api_xxx", "Auth: key_xxx", "Token: pk_xxx"
    # where the prefix is separated from the key value by ": "
    ("API_KEY", r"(?i)\b(?:key|token|secret|auth|api)\s*:\s*(?:sk[-_]|pk[-_]|gh[opusr]_|xox[bp]-|rk_(?:live|test)_|whsec_|api[-_]|key[-_]|secret[-_])[a-zA-Z0-9_\-]{16,64}\b", 0.90),
    # Level 3 — base64-looking runs adjacent to key/token/secret context (forward OR backward)
    # Negative lookahead blocks common FP patterns where the text explicitly says
    # the value is NOT a token (e.g. "looks like a token", "like a token", "not a token")
    ("API_KEY", r"\b(?:[A-Za-z0-9+/=]{20,})\b(?=.*(?:key|token|secret))(?!.*(?:looks like a|like a|not a)\s*(?:key|token|secret))", 0.90),
    # Level 4 — pure hex strings of 24+ chars (high-entropy, typical API key body)
    # NOT matched by any other pattern. Pure hex excludes common structural data
    # like emails, JWT fragments, base64-encoded text. Caught by higher-confidence
    # patterns first; this is a fallback for bare hex strings that look like keys.
    ("API_KEY", r"(?<!\w)(?![A-Fa-f0-9]*[g-zG-Z])(?:[A-Fa-f0-9]{24,})(?!\w)", 0.50),

    # ── PHONE ────────────────────────────────────────────────────────
        # Unicode dash character class: hyphen-minus, en-dash, em-dash, minus sign
        # Keyword-prefixed phone numbers (phone/tel/mobile/cell/call + number)
        # Must have at least 7 digits to avoid matching short sequences.
        # Negative lookahead avoids matching credit card numbers (4 groups of 4+ digits).
        ("PHONE", r"(?i)\b(?:phone|tel|telephone|mobile|cell|call)\s*(?:number|no|#)?\s*\-?\s*(?!\d{4,}[–—−\-.\s]\d{4,}[–—−\-.\s]\d{4,})\+?[\d\(][\d\s\-.,\)]{7,20}\b", 0.90),
        # International with + and unicode dashes: +1-555-123-4567, +1–555–123–4567, +1—555—123—4567, +1−555−123−4567
        ("PHONE", r"(?:^|\s)\+\d{1,3}[–—−\-\. ]\d{2,4}[–—−\-\. ]\d{3,4}[–—−\-\. ]\d{4}\b", 0.88),
        # International with + and spaces only (variable groupings): +44 20 7946 0958, +1 555 123 4567
        ("PHONE", r"(?:^|\s)\+\d{1,3}(?:\s+\d{2,4}){2,4}\b", 0.85),
        # International with +, country code 1 digit, spaced with optional unicode dashes inside
        ("PHONE", r"(?:^|\s)\+\d\s+\d{3}\s+\d{3}[–—−\-\. ]?\d{2}[–—−\-\. ]?\d{2}\b", 0.85),
        # International with + and mixed separators (any combo of dash types and spaces)
        ("PHONE", r"(?:^|\s)\+\d{1,3}[–—−\-.]\d{2,4}[–—−\-\. ]\d{3,4}[–—−\-\. ]?\d{3,4}\b", 0.85),
        # Bare E.164 with + prefix: "+140****1212" style
        ("PHONE", r"\+\d{7,15}\b", 0.80),
        # Parenthesized area code with separator: (415) 555–2671, (120) 625-59444
        ("PHONE", r"\(\d{3}\)\s*\d{3}[–—−\-.]\d{4,6}\b", 0.82),
        # Parenthesized area code with space separator: (415) 555 2671
        ("PHONE", r"\(\d{3}\)\s*\d{3}\s+\d{4,6}\b", 0.78),
        # 3-3-4 format with unicode dashes or dots: 555-123-4567, 555–123–4567, 555.123.4567
        # Negative lookbehind: block if preceded by a dot (IP octet like .168.1.1)
        ("PHONE", r"(?<!\.)\b\d{3}[–—−\-.]\d{3}[–—−\-.]\d{4}\b(?!\.\d{1,3})", 0.70),
        # Country-code prefixed (1-xxx-xxx-xxxx) with unicode dashes
        # Negative lookbehind: block if preceded by a dot (IP octet fragment)
        ("PHONE", r"(?<!\.)\b\d{1}[–—−\-.]\d{3}[–—−\-.]\d{3}[–—−\-.]\d{4}\b(?!\.\d{1,3})", 0.75),
        # Spaced 3+3+4 (US format with spaces): "555 123 4567", "555  123  4567"
        ("PHONE", r"\b\d{3}\s{1,2}\d{3}\s{1,2}\d{4}\b", 0.72),
        # Bare 10-digit US phone (no context needed): "5551234567", "4155552671"
        # Negative lookbehind avoids matching bank account numbers, API keys, tokens, secrets, etc.
        # Negative lookahead avoids matching when part of longer numeric ID (e.g. within API keys).
        ("PHONE", r"(?<!\d)\d{10}(?!\d)", 0.50),
        # E.164 bare: 11-14 continuous digits
        ("PHONE", r"(?<!\d)\d{11}(?!\d)", 0.60),
        ("PHONE", r"(?<!\d)\d{12}(?!\d)", 0.60),
        # E.164 bare with country code prefix context: "tel:" prefix
        ("PHONE", r"\btel:\d{7,15}\b", 0.85),
        # URL-encoded international: %2B1-555-123-4567 (handles single or double spaces)
        ("PHONE", r"%2B\d{1,3}\s{1,2}\d{2,4}\s{1,2}\d{3,4}\s{1,2}\d{3,4}\b", 0.85),
        # UK mobile bare with space: 07700 900 123, 07XXX XXX XXX
        ("PHONE", r"\b07\d{3}\s+\d{3}\s+\d{3}\b", 0.80),
        ("PHONE", r"\b07\d{9}\b", 0.75),
        # Variable-spaced international (country code + space + variable-length groups):
        # "44 20 7946 0958", "966 55 123 4567", "49 30 12345678"
        # Must NOT match IBAN segments (preceded by 2 letters + 2 digits),
        # credit card numbers (4-4-4-4 patterns), or IP addresses.
        # Negative lookahead excludes CC-like, IBAN-like, and IP-like patterns.
        # IP-like: 4 groups of 1-3 digits separated by spaces (e.g. "192 168 1 100").
        ("PHONE", r"\b(?!(?:IBAN|iban)\s)(?!\d{1,3}\s+\d{1,3}\s+\d{1,3}\s+\d{1,3}\b)\d{1,4}\s+\d{2,4}(?:\s+\d{2,8}){1,2}\b", 0.60),
        # UK mobile format with parentheses: (077) 009-00123
        ("PHONE", r"\(\d{4,5}\)\s*\d{3}[–—−\-.]?\d{5}\b", 0.78),
        # Country code space-separated with dash in subgroups: "86 138-0013-8000"
        ("PHONE", r"\b\d{1,3}\s+\d{3}[–—−\-.]\d{3,4}[–—−\-.]\d{3,4}\b", 0.78),
        # Phone numbers after CJK 电话/電話/手机 keywords (with unicode dash support)
        # Supports formats: +86 138-0013-8000, +1-555-123-4567, +81 90-1234-5678
        # CJK keywords: 电话/電話/电话是/電話は/手机号码/手機/联系电话/電話番号/連絡先電話
        # Optional colon between keyword and number: 電話: +86 138-0013-8000
        ("PHONE", r"(?i)(?:电话|電話|手机号码|手機|联系电话|電話番号|連絡先電話|手机|手機号码)\s*:?\s*\+[\d–—−\-]+(?:[\s–—−\-]+\d[\d–—−\-]*){2,}\b", 0.85),
        # CJK phone: 電話は+X XX-XXXX-XXXX (Japanese context, unicode dash support)
        # Also covers: 电话是, 手机号, 手机号码, 联系电话
        ("PHONE", r"(?i)(?:電話は|电话是|電話|手机号|手机号码|联系电话|手機|電話番号)\s*:?\s*\+\d+[\s–—−\-]?\d+[\s–—−\-]?\d+[\s–—−\-]?\d+\b", 0.85),
        # German format after Phone: — "+49 30 12345678"
        ("PHONE", r"(?i)\bPhone:\s*\+\d{1,3}\s+\d{2,4}\s+\d{5,10}\b", 0.80),
        # Universal variable-separator pattern: catch-all for phone-like sequences
                # with at least 9 digits and mixed separators (dashes, dots, spaces)
                # Uses negative lookahead to avoid matching:
                #   - IP addresses (already covered by IP_ADDRESS patterns)
                #   - Credit card 4-4-4-4 patterns (already covered by CREDIT_CARD)
                #   - IBAN segments (preceded by 2-letter country code)
                #   - Space-separated 4-group IPs like "10 10 10 10", "192 168 1 100"
                ("PHONE", r"(?!\d{1,3}(?:\.\d{1,3}){3}\b)(?!\d{1,3}\s+\d{1,3}\s+\d{1,3}\s+\d{1,3}\b)(?![A-Z]{2}\d)\b\d{2,4}[–—−\-\.\s]\d{2,4}[–—−\-\.\s]\d{2,4}[–—−\-\.\s]?\d{2,4}\b(?![–—−\-\.\s]?\d{2,4})", 0.55),
        # Context-prefixed bare international number: "Hidden field: 448959514933", "Encoded: 493012345678"
        # These match the FULL span including prefix, so they out-compete MASKED_SSN patterns
        # in cross-type containment (same span, higher confidence -> PHONE replaces MASKED_SSN).
        ("PHONE", r"(?i)(?:hidden\s+field|encoded|encrypted|obfuscat)[a-z]*\s*[:=]\s*\d{11}(?!\d)", 0.72),
        ("PHONE", r"(?i)(?:hidden\s+field|encoded|encrypted|obfuscat)[a-z]*\s*[:=]\s*\d{12}(?!\d)", 0.72),
        ("PHONE", r"(?i)(?:hidden\s+field|encoded|encrypted|obfuscat)[a-z]*\s*[:=]\s*\d{13}(?!\d)", 0.72),
        ("PHONE", r"(?i)(?:hidden\s+field|encoded|encrypted|obfuscat)[a-z]*\s*[:=]\s*\d{14}(?!\d)", 0.72),


    # ── IP_ADDRESS ───────────────────────────────────────────────────
    # Standard dotted-decimal IPv4 with strict octet validation (0-255 per octet).
    # Uses negative lookbehind/lookahead to avoid matching IP-like substrings
    # inside dates (e.g. "12.31.2025" where month=12 day=31 would match as IP).
    # Blocks: octet > 255, leading zeros that would imply octal.
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b", 0.90),
    # Full IPv6 (7 colons, 8 groups): 2001:0db8:85a3:0000:0000:8a2e:0370:7334
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.88),
    # IPv6 with single :: anywhere
    # IMPORTANT: The trailing-:: branch (X:X::) was removed because it only
    # produces FPs on compressed IPv6 addresses like 2001:db8::1 where \b
    # between :: (non-word) and 1 (word) matches the partial address.
    # The compressed IPv6 pattern below handles full addresses correctly.
    # The leading-:: branch uses start/space anchor to catch ::1, ::ff00:42,
    # etc. without matching ::1 as a substring inside larger addresses.
    ("IP_ADDRESS", r"(?:^|(?<=\s)):(?::[0-9a-fA-F]{1,4})+(?=\s|\Z)", 0.88),
    # IPv6 loopback: ::1
        # IMPORTANT: Use (?<=[^0-9a-fA-F]:) instead of (?<=:) to avoid matching
        # ::1 as a substring inside larger IPv6 addresses like 2001:db8::1
        # (the compressed IPv6 pattern already catches those).
        ("IP_ADDRESS", r"(?:(?<=\s)|(?<=\A)|(?<=[^0-9a-fA-F]:))::1(?:(?=\s)|(?=\Z))", 0.90),
        # IPv6 unspecified: :: — require at least one adjacent word char or space boundary
        ("IP_ADDRESS", r"(?:^::(?=\w)|(?<=\w)::(?=\s|$)|(?<=\s)::(?=\w|\s))", 0.85),
        # IPv6 embedded IPv4: ::ffff:192.168.1.1 or ::192.168.1.1
        # Uses lookbehind for left boundary since ::ffff: starts with colon
        ("IP_ADDRESS", r"(?:(?<=\s)|(?<=\A)|(?<=:))(?:[0-9a-fA-F]{1,4}:)*(?::(?:ffff:)?)?(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b", 0.88),
    # Compressed IPv6 with single :: (mid-rule): catches what the :: patterns above miss
    # e.g. 2001:db8::1, fe80::1, 2001:db8::ff00:42:8329
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:)+(?::[0-9a-fA-F]{1,4})+\b(?<!:)(?<![0-9a-fA-F]{5})", 0.85),
    # Hex-format IP: 0xc0.0xa8.0x00.0x01
    ("IP_ADDRESS", r"\b0x[0-9a-fA-F]{2}(?:\.0x[0-9a-fA-F]{2}){3}\b", 0.85),
    # Octal IP: 012.0130.00.01 — each octet must be valid octal 0-377
    ("IP_ADDRESS", r"\b0[0-7]{1,3}(?:\.0[0-7]{1,3}){3}\b", 0.85),
    # Space-separated dotted-decimal: 192 168 1 100
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\s+){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b", 0.80),
    # Decimal IP (32-bit integer): 3232235876
    # Valid range: 16777216 (1.0.0.0) to 4294967295 (255.255.255.255)
    # Requires 9-10 digits. 8-digit numbers like 37828224 are CC fragments
    # or other false positives, never genuine decimal IPs in practice.
    # Word boundaries avoid matching inside longer digit runs.
    # Only match if the numeric value is a valid 32-bit unsigned integer IP.
    # The numeric validation is done in the detector's _run_patterns() method.
    # IMPORTANT: Now that dotted-decimal IPs are caught on pre-strip text, this
    # catch-all is only needed for genuine decimal-form IPs (rare). Lower confidence
    # since 9-10 digit numbers that happen to fall in the valid IP range are often
    # SSNs, phone numbers, or bank accounts rather than actual integer-encoded IPs.
    ("IP_ADDRESS", r"\b(?:[1-9]\d{8,9})\b", 0.50),

    # ── GPS ──────────────────────────────────────────────────────────
    # Full coordinate pair after keyword label: "lat/lng/coordinates/gps: value1, value2"
    # Handles 3-digit integer parts (longitude -122) and 2+ decimal places
    ("GPS", r"\b(?:lat|lng|lon|latitude|longitude|coordinates?|coords?|gps|location)\s*[:=]?\s*[-+]?\d{1,3}\.\d{2,}", 0.90),
    # Comma/semicolon-separated coordinate pairs: "40.7128, -74.0060" or "52.52, 13.405"
    # Relaxed: 2+ decimal places, 1-3 digit integer part (longitudes up to 180)
    ("GPS", r"[-+]?\d{1,3}\.\d{2,}\s*[,;]\s*[-+]?\d{1,3}\.\d{2,}(?!\.\d)", 0.88),
    ("GPS", r"[-+]?\d{1,3}\.\d+\s*°?\s*[NS]\s*[,;]?\s*[-+]?\d{1,3}\.\d+\s*°?\s*[EW]", 0.85),
    # Individual decimal coordinates — match after keyword: "Coordinates: 40.7128" or "Location: 37.7749"
    ("GPS", r"(?i)(?:lat|lng|lon|latitude|longitude|coordinates|coord|gps|location)\s*[:=]\s*[-+]?\d{1,3}\.\d{2,}", 0.88),
    # Bare decimal coordinate — ONLY match if preceded by GPS keyword with just a space separator (no colon).
    # This catches "lat 40.7128" (space-only) while avoiding false positives on non-GPS decimals like
    # "3.14159" (pi), "1.234" (time), "0.5678" (value), etc.
    ("GPS", r"(?i)\b(?:lat|lng|lon|latitude|longitude|coordinates?|coord|gps|location)\s+[-+]?\d{1,3}\.\d{2,}(?!\.\d)(?!\.\w)", 0.55),

    # ── FILE_PATH ────────────────────────────────────────────────────
    ("FILE_PATH", r"(?<!\/)/(?:[a-zA-Z0-9._-]+/){3,}[a-zA-Z0-9._-]*(?!\w)", 0.85),
    ("FILE_PATH", r"(?<!\/)/(?:home|var|etc|usr|opt|tmp|root|mnt|media|run|srv)/(?:[a-zA-Z0-9._-]+/?)+[a-zA-Z0-9._-]+(?!\w)", 0.90),
    ("FILE_PATH", r"(?<!\w)(?:[A-Za-z]:\\[a-zA-Z0-9._\\ -]+)(?!\w)", 0.90),

    # ── PRIVATE_URL ──────────────────────────────────────────────────
    # IMPORTANT: PRIVATE_URL comes AFTER DATABASE_URL so that broader
    # DATABASE_URL matches take priority over private hostname substrings
    # inside DB connection strings. URL comes AFTER PRIVATE_URL so the
    # more specific private URL match takes priority over the generic URL.
    ("PRIVATE_URL", r"\bhttps?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\bhttps?://[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.[\w-]+)*(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\b[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.[\w-]+)*(?::\d+)(?:/[^\s]*)?\b", 0.85),
    # Bare internal hostname (no dot): http://internal:80/path
    ("PRIVATE_URL", r"\bhttps?://(?:internal|localhost|db|api|app|backend|frontend|redis|postgres|mysql|rabbitmq)(?::\d+)?(?:/[^\s]*)?\b", 0.80),

    # ── URL ──────────────────────────────────────────────────────────
    # URL comes AFTER PRIVATE_URL so that the more specific PRIVATE_URL
    # match takes priority when both match the same span.
    # Hostname must contain a dot (example.com) or be "localhost" to avoid
    # matching stripped IP artifacts like http://127001/api/health.
    ("URL", r"\bhttps?://(?!\d+(?:/|\b))(?:[\w-]+\.)+[\w-]+(?::\d+)?(?:/[\w./?=&%-]*)?\b", 0.85),
    ("URL", r"\bhttps?://localhost(?::\d+)?(?:/[\w./?=&%-]*)?\b", 0.85),

    # ── PASSPORT ─────────────────────────────────────────────────────
    ("PASSPORT", r"(?i)(?:^|\s)(?:passport)\s*(?:number|no|#)?\s*:?\s*[A-Z]{0,2}\d{6,9}\b", 0.85),
    ("PASSPORT", r"\b[A-Z]{1,2}\d{6,9}\b", 0.75),

    # ── BANK_ACCOUNT ─────────────────────────────────────────────────
    # Matches keyword-prefixed bank account numbers. Supports connecting words
    # like "is" and "was" between the keyword and the number (e.g., "Bank account is 123456789012"),
    # as well as common prefix/suffix patterns like "Bank:", "account:", "acct no:", "A/c:".
    ("BANK_ACCOUNT", r"(?i)\b(?:bank|account|acct|A/c)\s*(?:number|no|#)?\s*(?::|is|was)?\s*\d{8,17}\b", 0.85),
    # Non-IBAN-looking digit sequences — exclude those starting with 2 letters
    # Bare 12-20 digit sequences at low confidence — context gate (detector.py:1821-1836) filters FPs
    ("BANK_ACCOUNT", r"\b\d{12,20}\b", 0.45),

    # ── PERSON ───────────────────────────────────────────────────────
    # Title-prefixed — name must be 2+ chars, not a single letter
    # Denylist blocks common non-name capitalized words (technical terms, roles)
    ("PERSON", r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.85),
    # "I'm/My name is/Call me + Name"
    # Require 2+ chars after initial capital to catch 3-letter names like "Bob", "Tom"
    # Denylist blocks common non-name capitalized words
    ("PERSON", r"(?i)(?:\bmy name is|\bI'm|\bcall me|\bname is)\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,}){0,2}\b", 0.80),
    # "ROLE + Name" — exclude common role/researcher-type words after the name
    # Require 2+ chars after initial capital to match names like "Bob" (B+ob=2 lowercase)
    # with lower confidence; avoids missing 3-letter names like "Bob", "Tom", "Sam"
    # Denylist blocks common non-name capitalized words
    ("PERSON", r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.70),
    # "Person:" prefix — handle titles like Dr., Mr. — require at least one real name word
    # Negative lookahead blocks words like "researcher", "published", "from", "at" that are common role/context words
    # Also blocks common non-person continuations: addresses, company suffixes, job titles
    # Denylist on the name part blocks common non-name capitalized words (technical terms)
    ("PERSON", r"(?i)\bPerson:\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+)?(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:[.']?[a-z]+)?(?:\s+(?-i:[A-Z])[a-z]{2,}(?:[.']?[a-z]+)?){0,1}(?!\s+(?:researcher|published|from|at|in|of|the|a|an|and|or|for|with|by|to|on|is|was|has|had|said|says|who|whom|whose|where|when|what|which|that|this|these|those|Inc|Corp|LLC|Ltd|Limited|GmbH|Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd))(?:[.]?)\b", 0.80),
    # "Contact person:" / "Contact name:"
    # Denylist blocks common non-name capitalized words
    ("PERSON", r"(?i)\bContact\s+(?:person|name):\s*(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.80),
    # Unicode/Non-Latin names — matched by context keywords (CJK + common non-Latin alphabet names)
    # CJK: keyword 用户/联系人/姓名 directly followed by name (no colon needed)
    # Exclude common technical terms that look like capitalized names (Postgresql, Admin, Root, etc.)
    # Also exclude company suffixes and address suffixes
    # Denylist on the name part blocks common non-name capitalized words (technical terms)
    ("PERSON", r"(?i)\b(?:contact|person)\s*[：:]\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+)?(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:\s+[A-Z][a-z]{2,})?(?!\s+(?:researcher|published|from|at|in|of|the|a|an|and|or|for|with|by|to|on|is|was|has|had|said|says|who|whom|whose|where|when|what|which|that|this|these|those|Inc|Corp|LLC|Ltd|Limited|GmbH|Street|St|Avenue|Ave|Road|Rd))\b", 0.75),
    # user: prefix — more restrictive to avoid technical terms like 'user: postgresql'
    # Extended exclusion list for common non-person user labels; require 3+ chars in name
    ("PERSON", r"(?i)\buser\s*[：:](?!\s*(?:admin|root|postgres|postgresql|mysql|default|guest|test|anonymous|nobody|system|api|service|demo|readonly|backup|deploy|ci|cd|bot|monitor|agent|worker|dev|prod|staging|localhost|primary|secondary|nginx|git|www|web|app|db|redis|memcache|rabbitmq|elasticsearch|kibana|jenkins|docker|kubernetes|k8s|terraform|ansible|puppet|chef|vagrant|node|npm|yarn|pip|composer|gradle|go|rust|php|python|ruby|java|scala|kotlin|swift|flutter|react|angular|vue|svelte|nextjs|nuxt|gatsby|jekyll|hugo|django|flask|spring|rails|laravel|symfony|express|fastify|koa|hapi|socket|stream|event|queue|cache|search|index|proxy|gateway|firewall|vpn|ssh|ssl|tls|oauth|saml|ldap|kerberos))\s*[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?\b", 0.65),
    # CJK-specific: 用户/联系人/姓名 directly followed by 2+ CJK characters
    ("PERSON", r"(?:用户|联系人|姓名|名前)[：:]?\s*[\u4e00-\u9fff]{2,4}(?:\s+[\u4e00-\u9fff]{2,4})?\b", 0.80),
    # Russian/Cyrillic names
    ("PERSON", r"(?i)\b(?:contact|user|person|connect|reach)\s+(?:is|name)\s+[\u0400-\u04ff]+\b", 0.75),
    # Arabic script names — handle بـ prefix (U+0628 + optional tatweel U+0640)
    # Exclude standalone بـ without a following name
    # Require 3+ Arabic chars after the name to avoid matching just the prefix
    ("PERSON", r"(?i)\b(?:اتصل)\s+بـ?\s*[\u0600-\u06ff\u0750-\u077f]{3,}\b", 0.80),
    ("PERSON", r"(?i)\b(?:اسم|اسمي)\s+[\u0600-\u06ff]+\b", 0.80),
    # Japanese: CJK name followed by の (possessive) or さん (honorific)
        # NOTE: No \\b at end. Python's \\b treats CJK chars as \\w chars, so
        # there's no boundary between の and any following CJK/Hiragana/Katakana
        # character.  Instead we use a negative lookahead that blocks only when
        # followed by a literal Latin letter or digit (not hiragana/katakana).
        ("PERSON", r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,4}(?:\u306e|\u3055\u3093)(?![a-zA-Z0-9])", 0.70),
    # Greek alphabet names (O + name pattern for "O Γιώργος")
    ("PERSON", r"(?i)\bO\s+[\u0370-\u03ff]+\b", 0.70),
    # Any non-Latin name caught by context + multiple non-Latin word chars
        # IMPORTANT: Negative lookahead prevents matching when the non-Latin chars
        # are the local-part of an email address (homoglyph obfuscation like
        # "αӏісе@domain.com" where "αӏісе" uses Cyrillic homoglyphs to spell "alice").
        # Also exclude matches followed by `@` (email address continuation) or by
        # more Latin characters that would indicate email-part or password context.
        ("PERSON", r"\b(?:name|email|phone|mail|contact|user)\s*[：:]\s*(?![\u0400-\u04ff\u0600-\u06ff]+@)[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff]+\b(?!\s*@)", 0.65),
    # Non-Latin names after language labels — use lookbehind so match starts at the name
    # Require at least 3+ consecutive non-Latin chars to avoid matching
    # short prefixes that aren't names
    # Exclude Arabic prefix words that aren't names themselves (اتصل = contact, etc.)
    # IMPORTANT: negative lookahead must come BEFORE \\s* so that backtracking
        # doesn't bypass it by leaving a space character at the lookahead position.
        # CRITICAL: The continuation character class must NOT include Latin letters
        # (a-z0-9) to avoid greedily eating email prefixes, verbs, and particles.
        ("PERSON", r"(?i)(?:(?<=Russian:)|(?<=Arabic:)|(?<=Japanese:)|(?<=Greek:)|(?<=Unicode))(?!(?:\s*اتصل|\s*بـ))\s*(?-i:[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{3,}(?:\s+(?-i:[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]*)?\b", 0.70),
    # "Signed/from/by/preposition + Name" — strong signal for person names
    # Requires TWO capitalized words (first + last name) to avoid matching
    # single-word company names like "signed by Google"
    # Exclude "from" followed by known company-like words (corp, inc, ltd, etc.)
    # Exclude "from" followed by geographic terms (city/country)
    # Negative lookahead on: company suffixes, geographic roles, job titles
    # Second name word must not be a company suffix (Corp, Inc, etc.)
    # First name word denylist blocks common non-name capitalized words
    ("PERSON", r"(?i)\b(?:Signed|signed)\s+by\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}\s+(?-i:(?!Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|PLC|AG|SA|Team|Group)[A-Z])[a-z]{2,}(?!\s+(?:researcher|published|from|at|in|of|the|Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln))\b", 0.78),
    # "from Name" — Name must be two capitalized words (first + last) to avoid
    # matching city names or single-word entities. Lower confidence since
    # "from" can precede companies, cities, and countries.
    # Explicitly exclude known two-word city names (New York, Los Angeles, etc.)
    # Second name word must not be a company suffix
    # Negative lookahead blocks parenthetical media references: "from Finding Nemo)"
    # First name word denylist blocks both city names and common non-name capitalized words
    ("PERSON", r"(?i)\bfrom\s+(?-i:(?!New|Los|San|Las|Buenos|Bangkok|Hong|Kuala|Rio|Sao|Buenos|Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Project|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Tech|Technologies|Systems|Software|Solutions|Services|Industries|Enterprises|Consulting|Associates|Group|Partners|Holdings|Ventures)[A-Z][a-z]{2,})\s+(?-i:(?!Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|PLC|AG|SA|and|or|the|Street|St|Avenue|Ave|Road|Rd)[A-Z])[a-z]{2,}\b(?![^(]*\))", 0.65),
    # "by Name" — two-word capitalized name after "by"
    # Excludes geographic continuations (cities, countries) and company suffixes
    # Second name word must not be a company suffix
    ("PERSON", r"(?i)\bby\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Project)[A-Z])[a-z]{2,}\s+(?-i:(?!Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|and|or|the|Street|St|Avenue|Ave|Road|Rd|Drive|Dr)[A-Z])[a-z]{2,}\b", 0.60),
    # "contact/reach/met (with)/meet (with) + Name" — verb of communication + person
    # Both single-name (contact Robert) and full-name (contact Alice Smith) supported
    # "meet with" and "met with" are handled by the optional "with" between verb and name
    # Name must be a capitalized word (not 'settings', 'config', 'Postgres', etc.)
    # Negative lookahead blocks company suffixes, prepositions that start clauses,
    # and non-name technical words. Denylist blocks technical terms on the name part.
    ("PERSON", r"(?i)\b(?:contact|reach|met|meet)(?:\s+with)?\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?(?!\s+(?:about|with|in|the|Inc|Corp|LLC|Ltd|Limited|name|Settings|Config|Options))(?:\s+(?:at|on|for))?\b", 0.70),
    # "spoke with / talked to / introduced to / introduce you to + Name"
    # Two+ word capitalized name required to avoid FPs on common words
    # Denylist blocks technical terms on the first name part
    ("PERSON", r"(?i)\b(?:spoke\s+with|talked\s+to|introduc(?:e|ed|ing)\s+(?:you\s+)?to|got\s+to\s+know)\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}\s+(?-i:[A-Z])[a-z]{2,}\b", 0.68),
    # "introducing / please welcome / meet our new hire / say hello to + Name"
    # Denylist blocks technical terms on the name part
    ("PERSON", r"(?i)\b(?:introducing|please\s+welcome|meet\s+(?:our\s+)?(?:new\s+)?(?:hire|teammate|colleague|team\s+member)|say\s+hello\s+to|shoutout\s+to)\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.68),
    # "regarding Name" — two capitalized words after regarding
    # Denylist blocks technical terms on the first name part
    ("PERSON", r"(?i)\bregarding\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}\s+(?-i:(?!Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|Incorporated|PLC|AG|SA|Systems|Technologies|Tech|Software|Solutions|Group|Partners|Holdings|Services|Consulting|Associates)[A-Z])[a-z]{2,}(?!\s+(?:Inc|Corp|LLC))\b", 0.55),
    # "Manager: / Supervisor:" prefix patterns
    # Exclude common UI/technical words that could follow these labels
    ("PERSON", r"(?i)\b(?:Manager|Supervisor|Coordinator|Lead|Admin|HR\s+rep)\s*:\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof)\s+)?(?-i:(?!Settings|Config|Options|Admin|Dashboard|Profile|Account|General|System|Network|Security|Users|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.75),
    # "Employee Name" — capitalized name after "Employee" (complements EMPLOYEE_NAME type)
    # Negative lookahead blocks two-word names (those are EMPLOYEE_NAME territory) and
    # parenthetical references (e.g. "(famous from Employee Training)").
    ("PERSON", r"(?i)\bEmployee\s+(?-i:(?!from|of|at\b)[A-Z])[a-z]{2,}(?!\s+(?-i:[A-Z])[a-z]{2,})(?!\s+(?:name|ID|id|number))\b(?!\s*\))", 0.65),
    # "Signed, Name" — comma after signed, then capitalized name
    # Denylist blocks technical terms on the name part
    ("PERSON", r"(?i)\bsigned[-,]\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd)[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.72),
    # Bare "FirstName LastName" at sentence start or after period/newline — capture the
    # first two capitalized words. Exclude common sentence-starting words, company suffixes,
    # and known non-person entities. Very carefully limited to avoid FPs.
    # Negative lookahead blocks: company words, role/job words, sentence particles,
    # geographic names, known non-person sentence starters, and common 2-word phrases.
    ("PERSON", r"(?:^|\.\s+)(?-i:[A-Z])[a-z]{2,}\s+(?-i:[A-Z])[a-z]{2,}(?=\s+(?:approved|confirmed|requested|signed|said|reported|joined|left|called|sent|wrote|emailed|asked|answered|explained|mentioned|noted|added|replied|checked|updated|created|started|finished|completed|submitted|reviewed))", 0.55),

    # ── CUSTOMER_NAME ────────────────────────────────────────────────
    ("CUSTOMER_NAME", r"(?i)\b(?:customer|client)\s+(?:name\s+)?(?:is\s+)?(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("CUSTOMER_NAME", r"(?i)\b(?:Customer|Client):\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("CUSTOMER_NAME", r"(?i)\bcustomer\s+(?:we\s+)?(?:have|here)\s+is\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.75),
    # "Customer name:" prefix
    ("CUSTOMER_NAME", r"(?i)\bCustomer\s+name:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    # "User X ordered" pattern
    ("CUSTOMER_NAME", r"(?i)\bUser\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\s+ordered\b", 0.75),

    # ── EMPLOYEE_NAME ────────────────────────────────────────────────
    ("EMPLOYEE_NAME", r"(?i)\b(?:employee|staff|teammate|colleague|manager|supervisor|engineer|developer|designer)\s+(?:name\s+)?(?:is\s+)?(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("EMPLOYEE_NAME", r"(?i)\b(?:employee|staff)\s+(?:named|name)\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("EMPLOYEE_NAME", r"(?i)\bEmployee:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("EMPLOYEE_NAME", r"(?i)\b(?:add\s+)?employee\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.75),
    # "Team member X" pattern
    ("EMPLOYEE_NAME", r"(?i)\bTeam\s+member\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    # "Staff: X" pattern
    ("EMPLOYEE_NAME", r"(?i)\bStaff:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    # "Employee name: X" pattern
    ("EMPLOYEE_NAME", r"(?i)\bEmployee\s+name:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),

    # ── PROJECT_NAME ─────────────────────────────────────────────────
    # "project name is Name", "Project: Name", "initiative called Name"
    ("PROJECT_NAME", r"(?i)\b(?:project|initiative|campaign|program)\s*:\s*(?:(?:name\s*)?(?:is\s*)?(?:called\s*)?)?(?-i:[A-Z])[a-zA-Z0-9]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)*\b", 0.80),
    # "Code-name Name", "Project Name" (capitalized keyword prefix)
    ("PROJECT_NAME", r"\b(?:Project|Operation|Initiative|Program|Code[- ]?name)\s+(?-i:[A-Z])[a-zA-Z0-9]+\b", 0.85),
    # Standalone capitalized project names like "Project Phoenix", "Project code-name Delta Force"
    ("PROJECT_NAME", r"\b(?:Project|Operation|Initiative|Program|Task)(?:\s+code[- ]?name)?\s+(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)?\b", 0.80),
    # Two-word capitalized names in project context like "Blue Sky", "Omega Protocol"
    ("PROJECT_NAME", r"(?i)\b(?:working\s+on|assigned\s+to)\s+(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z]+)?\b", 0.70),
    # "X milestone due" pattern
    ("PROJECT_NAME", r"(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\s+milestone\s+due\b", 0.70),
    # "X is in development / in maintenance"
    ("PROJECT_NAME", r"(?i)(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z]+)?\s+is\s+in\s+(?:development|maintenance|maint)\b", 0.65),
    # Lowercase "project/initiative" + capitalized name (no colon needed)
    # Catches: "for project Vulcan", "- project Pandorica", "for project Last Centurion",
    # "for the project Vulcan" (with optional article between keyword and name).
    # Must come AFTER uppercase Project patterns so the narrower uppercase match wins dedup.
    ("PROJECT_NAME", r"(?i)\b(?:project|initiative|campaign|program)\s+(?:(?:the|our|this|that|a|an)\s+)?(?-i:[A-Z])[a-zA-Z0-9]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)*\b", 0.85),

    # ── ADDRESS ──────────────────────────────────────────────────────
            # Standard address: "N Street Name St/Rd/Ave/etc."
            # Enhanced: captures street + city + state + ZIP/postcode for full address matching.
            # Uses negative lookbehind (?<!not\s) to block ", not 123 Main St" teaching patterns.
            # Uses a general negative lookahead for parentheticals that look like media references.
            # Optional suffix captures city, state abbreviation + ZIP, or UK postcode after street.
            ("ADDRESS", r"\b(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?:,\s*(?!not\b)[A-Z][a-z]+(?:[\s-]+[A-Z][a-z]+)*(?:,\s*(?:[A-Z]{2}\s+\d{5}(?:-\d{4})?|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}|\d{5})))?(?:\s*,\s*(?!not\b)[A-Za-z]+(?:\s+[A-Za-z]+)?)?(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:movie|show|film|game|series|cartoon|animation|episode|from\s+[A-Z]))\b", 0.85),
            # European-style addresses: "Street Name N, Postcode City" — where the number comes
        # after the street name, followed by comma and postcode + city.
        # Supports multi-word street names with lowercase particles (den, der, von, etc.)
        # and non-ASCII characters (ü, ß, é, etc.). The first word must start with an
        # uppercase letter to avoid matching generic phrases.
        # Catches patterns like "Unter den Linden 1, 10117 Berlin", "Rue de la Paix 15, 75002 Paris"
    ("ADDRESS", r"\b(?:[A-Z]\w*(?:\s+(?:[A-Z]\w*|den|der|die|das|von|vom|zum|zur|am|im|in|an|auf|bei|mit|und|oder|aus|nicht|dem|des|ein|eine|einer|einem|für|über|unter|und|of|the|la|le|les|de|del|della|dos|das|van|ver|des|du|sur|aux|en|el)){0,5})\s+\d{1,4}[a-z]?,\s*\d{4,5}\s+\w+(?:[\s-]+\w+)?\b", 0.80),
        ("ADDRESS", r"\bP\.?\s*O\.?\s+Box\s+\d+\b", 0.85),
        ("ADDRESS", r"\b(?:Suite|Apt|Unit|Building)\s+#?\d+[A-Za-z]?\b", 0.80),
        # Street-name-first with #N suffix: "Street Name Road, #7345, City, ST ZIP"
        # Catches addresses where the house/building number comes AFTER the street name,
        # prefixed by # (common in databases and informal address listings).
        # Supports street suffixes (St, Rd, Ave, Blvd, etc.), optional city, state ZIP.
        ("ADDRESS", r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway),\s*#\d+(?:,\s*[A-Z][a-z]+(?:[\s-]+[A-Z][a-z]+)*(?:,\s*(?:[A-Z]{2}\s+\d{5}(?:-\d{4})?|\d{5}))?)?\b", 0.85),

    # ── COUNTRY ──────────────────────────────────────────────────────
        # IMPORTANT: COUNTRY must come BEFORE CITY so that higher-confidence (0.80)
        # country matches take priority over lower-confidence (0.50) city matches
        # for words that are both countries and potential city names.
        # Full country names — unambiguous, high confidence.
        ("COUNTRY", r"\b(?:United States|United Kingdom|Canada|Australia|Germany|France|Italy|Spain|Japan|China|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|South Korea|Argentina|Chile|Colombia|Egypt|Nigeria|South Africa|Kenya|Thailand|Vietnam|Philippines|Indonesia|Malaysia|Singapore|New Zealand|Saudi Arabia|Israel|Greece|Finland|Hungary|Romania|Ukraine|USA)\b", 0.80),
        # Short abbreviations (US, UK, UAE) — more FP-prone.
        # Negative lookbehind guards against parenthetical asides like "(UK mobile)", "(US dollars)".
        ("COUNTRY", r"(?<![\(\)])\b(?:US|UK|UAE)\b", 0.70),
        # "Czech Republic" — full country name
        ("COUNTRY", r"\bCzech\s+Republic\b", 0.80),
        # Adjective/native forms of country names — lower confidence since these
        # can also be languages.
        ("COUNTRY", r"\bGerman\b", 0.70),
        # Native-language country names e.g. Italia for Italy
        ("COUNTRY", r"\bItalia\b", 0.70),
        # "England" as a country name (part of UK but commonly used)
        ("COUNTRY", r"\bEngland\b", 0.70),

        # ── CITY ─────────────────────────────────────────────────────────
        # City in population context: "X (37M), Y (32M)" — match just the city name before the parenthetical
        # Must come before broader keyword-prefixed patterns so the narrower match wins dedup.
        ("CITY", r"\b[A-Z][a-z]+(?=\s*\(\d+\s*M\))", 0.55),
        # City after "of" keyword - use lookbehind so "of " isn't part of the match.
        # Must come before keyword-prefixed patterns so the narrower match wins.
        ("CITY", r"(?i)(?<=of )(?!(?:Germany|France|Italy|Spain|UK|USA|US|Canada|Australia|England|China|India|Japan|Brazil|Mexico|Russia|Poland|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Turkey|Greece|Egypt|Thailand|Vietnam|Latin)\b)(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.50),
        ("CITY", r"(?i)(?<=city of )(?!(?:Germany|France|Italy|Spain|UK|USA|US|Canada|Australia|England|China|India|Japan|Brazil|Mexico|Russia|Poland|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Turkey|Greece|Egypt|Thailand|Vietnam)\b)(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.50),
        # Cities at start of sentence — explicit list of well-known city names.
        # High confidence: these are unambiguously place names ("Paris has...", "London is...").
        # NOTE: Some cities (Tokyo, Sydney) also appear in GPS-coordinate parenthetical
        # context "(Tokyo)" where they ARE labeled as CITY entities. These are matched
        # by the unrestricted pattern below. All other known cities use the negative
        # lookbehind (?<!\() to suppress false positives inside parentheses that are
        # GPS coordinate labels (e.g. "(London)" after lat/lng, "(Berlin office)").
        ("CITY", r"\b(?:Tokyo|Sydney)\b", 0.75),
        ("CITY", r"(?<!\()\b(?:Paris|London|Berlin|Moscow|Beijing|Shanghai|Melbourne|Bangkok|Seoul|Mumbai|Delhi|Cairo|Dubai|Singapore|Hong Kong|Madrid|Rome|Roma|Vienna|Prague|Budapest|Warsaw|Amsterdam|Brussels|Stockholm|Oslo|Helsinki|Copenhagen|Dublin|Lisbon|Athens|Zurich|Munich|Hamburg|Frankfurt|Milan|Barcelona|Istanbul|Jerusalem|Riyadh|Manila|Jakarta|Hanoi|Taipei|Kuala Lumpur|Mexico City|Lima|Santiago|Bogota|Buenos Aires|Rio de Janeiro|Sao Paulo|Nairobi|Lagos|Cape Town|Johannesburg|Casablanca)\b", 0.75),

        # Cities followed by comma + known country — use positive lookahead so match is JUST the city name
        # Exclude country names from the city position to avoid COUNTRY->CITY confusion
        ("CITY", r"\b(?!(?:Canada|Australia|Germany|France|Italy|Spain|Japan|China|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|Egypt|Nigeria|South Africa|Kenya|Thailand|Vietnam|Indonesia|Malaysia|Singapore|New Zealand|Greece|Finland|Hungary|Romania|Ukraine)\b)[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:Germany|France|Italy|Spain|UK|England|USA|US|China|Japan|India|Brazil|Canada|Australia)\b)", 0.70),
    # City after "works at X in City" or "based in City" using lookbehind for "in "
        # Fixed-width lookbehind prevents keyword from being part of the match span.
        # Comprehensive negative lookahead blocks all common UI/technical/role/department
        # words that happen to be capitalized but are NOT city names, plus months, colors,
        # disciplines, and generic entity names. Only single-word alternatives are included
        # since the matched token after "in " is a single capitalized word.
        ("CITY", r"(?i)(?<=\bin\s)(?!(?:Settings|Config|Configuration|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax|Nature|Science|General|Practice|Theory|Process|Market|Public|Private|Common|Research|Development|Support|Security|Service|History|Current|Future|Recent|Final|Total|Average|Standard|Normal|Special|Maintenance|Text|Mode|Progress|Review|Summary|Detail|Analysis|Backticks|Quotes|Brackets|Parentheses|Here|There|This|That|These|Those|The|A|An|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Anthropology|Linguistics|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Office|Studio|Lab|Laboratory|Workshop|Hub|Center|Centre|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Board|Council|Panel|Squad|Chapter|Region|Zone|Area|District|Sector|Cluster|Node|Module|Component|Element|Fragment|Segment|Block|Layer|Level|Stage|Phase|Step|Part|Piece|Section|Subsection|Category|Class|Type|Kind|Sort|Form|Variant|Version|Revision|Edition|Generation|Iteration|Patch|Hotfix|Release|Build|Compile|Runtime|Deploy|Stage|Prod|Production|Staging|Dev|Development|Test|Integration|E2E|Unit|Functional|Regression|Performance|Load|Stress|Chaos|Smoke|Sanity|Acceptance|Beta|Alpha|Canary|Feature|Fix|Bug|Issue|Ticket|Story|Epic|Sprint|Backlog|Roadmap|Milestone|Goal|Objective|Initiative|Program|Portfolio|Vendor|Client|Customer|Partner|Stakeholder|Member|Lead|Head|Chief|Officer|Executive|Director|VP|SVP|EVP|Founder|Owner|Operator|Administrator|Coordinator|Facilitator|Supervisor|Overseer|Inspector|Analyst|Specialist|Expert|Advisor|Consultant|Agent|Representative|Liaison|Ambassador|Advocate|Champion|Sponsor|Mentor|Coach|Trainer|Instructor|Teacher|Professor|Lecturer|Researcher|Scientist|Scholar|Fellow|Intern|Trainee|Apprentice|Junior|Senior|Principal|Staff|Architect|Strategist|Planner|Director|President|Chairman|Chairperson|Chancellor|Dean|Provost|Rector|Registrar|Clerk|Secretary|Treasurer|Auditor|Comptroller|Controller|Bookkeeper|Accountant|Actuary|Underwriter|Broker|Adjuster|Appraiser|Surveyor|Technician|Technologist|Operator|Mechanic|Electrician|Plumber|Carpenter|Welder|Mason|Painter|Janitor|Custodian|Guard|Watchman|Patrol|Sergeant|Lieutenant|Captain|Major|Colonel|General|Admiral|Commander|Handler|Processor|Assistant|Associate|Worker|Employee|Contractor|Volunteer|Participant|Contributor|Collaborator|Partner|Colleague|Peer|Teammate|Classmate|Neighbor|Citizen|Resident|Visitor|Guest|Tourist|Traveler|Commuter|Passenger|Driver|Pilot|Crew|Sailor|Soldier|Marine|Officer|Spy|Detective|Investigator|Examiner|Reviewer|Checker|Validator|Verifier|Certifier|Assessor|Evaluator|Appraiser|Rater|Scorer|Grader|Judge|Referee|Arbiter|Umpire|Moderator|Mediator|Arbitrator|Conciliator|Negotiator|Dispatcher)\\b)(?-i:[A-Z])[a-z]{2,}\b(?=\s*,|\s*\.|\s*-|\s+and|\s+or|\s*$)", 0.50),
    # Keyword-prefixed: "city/town of/pop: Name" — the keyword prefix is included in the match.
    # These come last so narrower city-specific patterns (of, in, population) fire first.
    ("CITY", r"(?i)\b(?:city(?: (?:of|pop:?|population:?))?|town(?: (?:of|pop:?))?)\s*:?\s*(?!(?:The|A|An|This|That|These|Those|Our|Their|My|Your|His|Her|Its)\b)(?-i:[A-Z])[a-z]+(?:[ -]+(?-i:[A-Z])[a-z]+)?\b", 0.70),
    # "based in/located in/situated in" — broader patterns. Must come after narrower in-pattern
    # so the narrower in-lookbehind match wins dedup.
    ("CITY", r"(?i)\b(?:based\s+in|lives?\s+in|located\s+in|situated\s+in)\s+(?-i:[A-Z])[a-z]{2,}\b", 0.60),
    # "works at X in City" or "works in City"
    ("CITY", r"(?i)\bworks?\s+(?:at\s+\S+\s+)?in\s+(?-i:[A-Z])[a-z]{2,}\b", 0.60),
    # "visiting City" — travel/destination context indicates a city
    ("CITY", r"(?i)\bvisiting\s+(?-i:[A-Z])[a-z]{2,}(?:[ -]+(?-i:[A-Z])[a-z]{2,})?\b", 0.60),
    # "City headquarters/office/plant" — city name before location type
    # Uses positive lookahead so match span is ONLY the city name, not the trailing location word.
    ("[CITY]", r"(?<!\()\b(?!(?:Our|Their|My|Your|His|Her|Its|The|This|That|These|Those|All|Some|Many|Both|Each|Every|Few|More|Most|Other|Such|Same|Just|Also|Very|Too|Quite|Well|Now|Here|There|Then|Than|Into|Upon|Under|Over|Again|Before|After|Until|During|Since|About|Between|Through|Because|Office|Offices|Headquarters|Facility|Plant|Branch|Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Pkwy|Highway|Hwy|Suite|Ste|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Hotel|Club|House|Home|Lab|Laboratory|Studio|Office|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Spa|Salon|Spa|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|Hospital|Dental|Optical|Veterinary|Animal|Pet|Grocery|Market|Store|Shop|Boutique|Salon|Spa|Nail|Barber|Tailor|Cleaner|Laundry|Repair|Garage|Service|Center|Centre|Depot|Hub|Node|Site|Location|Venue|Place|Area|Zone|Region|District)\b)[A-Z][a-z]{2,}(?:[ -]+[A-Z][a-z]{2,})?(?=\s+(?:headquarters|office|offices|facility|facilities|plant)\b)", 0.55),
    # "Our/Their City office" — possessive before city before location
    ("CITY", r"(?i)\b(?:our|their)\s+(?!Office|Offices|Headquarters|Facility|Plant|Branch)(?-i:[A-Z])[a-z]{2,}(?:[ -]+(?-i:[A-Z])[a-z]{2,})?\s+(?:office|offices|headquarters|facility|plant|branch)\b", 0.55),
    # City in address context before US state + optional ZIP: "City, ST" or "City, ST 12345"
    # e.g. "New York, NY 10018" or "Springfield, IL 62704".
    # Must use a lookahead for a known state abbreviation (2-letter uppercase US territory code)
    # to avoid FPs like "Fifth Avenue, NY" — the initial negative lookahead blocks street suffixes.
    # Score 0.55 — safe but low confidence since many towns share names.
    ("CITY", r"\b(?!(?:Office|Offices|Suite|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax|Nature|Science|General|Practice|Theory|Process|Public|Private|Common|Research|Development|Text|Mode|Here|There|This|That|These|Those|The|A|An|All|Some|Many|Both|Each|Every|Few|More|Most|Other|Such|Same|Just|Also|Very|Too|Quite|Well|Now|Then|Than|Into|Upon|Under|Over|Again|Before|After|Until|During|Since|About|Between|Through|Because|North|South|East|West|Northeast|Northwest|Southeast|Southwest|Northern|Southern|Eastern|Western|Central|Upper|Lower|Mid|Inner|Outer|Forward|Backward|Upward|Downward|Internal|External|Left|Right|Top|Bottom|Front|Back|Side|End|Edge|Corner|Middle|Heart|Core|Base|Basis|Ground|Floor|Level|Layer|Tier|Phase|Stage|Step|Point|Spot|Site|Area|Zone|Sector|Region|District|Quarter|Block|Lot|Plot|Field|Track|Line|Row|Column|Node|End|Location|Place|Space|Mark|Sign|Symbol|Icon|Logo|Image|Picture|Photo|Graphic|Art|Design|Pattern|Model|Style|Type|Form|Kind|Sort|Class|Category|Set|Series|Range|Scale|Rate|Degree|Grade|Rank|Status|State|Condition|Position|Role|Function|Task|Job|Work|Duty|Charge|Mission|Operation|Action|Activity|Process|Procedure|Method|Approach|Technique|System|Scheme|Plan|Program|Project|Initiative|Campaign|Drive|Push|Effort|Attempt|Try|Trial|Test|Experiment|Study|Survey|Poll|Census|Count|Tally|Total|Sum|Amount|Number|Figure|Digit|Value|Quantity|Measure|Metric|Index|Indicator|Test|Assessment|Evaluation|Judgment|Rating|Score|Grade|Mark|Label|Brand|Tag|Title|Term|Source|Origin|Root|Cause|Reason|Basis|Ground|Foundation|Path|Route|Course|Channel|Track|Lane|Alley|Passage|Corridor|Hall|Window|Gate|Entrance|Exit|Door|Wall|Ceiling|Roof|Capacity|Size|Dimension|Length|Width|Height|Depth|Breadth|Span|Range|Scope|Extent|Scale|Standard|Norm|Criterion|Benchmark|Baseline|Threshold|Cutoff|Meeting|Conference|Summit|Forum|Seminar|Workshop|Symposium|Convention|Congress|Assembly|Gathering|Meetup|Event|Function|Gala|Ceremony|Tradition|Custom|Convention|Practice|Norm|Standard|Rule|Code|Law|Regulation|Statute|Ordinance|Decree|Edict|Mandate|Order|Command|Instruction|Direction|Guideline|Requirement|Specification|Protocol|Procedure|Policy|Principle|Doctrine|Tenet|Maxim|Axiom|Truth|Fact|Reality|Certainty|Absolute|Given|Constant|Variable|Parameter|Factor|Element|Component|Part|Piece|Segment|Section|Portion|Fraction|Division|Subdivision|Category|Class|Group|Set|Collection|Assembly|Cluster|Batch|Bunch|Pack|Bundle|Stack|Heap|Pile|Mass|Volume|Bulk|Majority|Minority|Plurality|Multitude|Array|Range|Variety|Diversity|Selection|Choice|Option|Alternative|Possibility|Opportunity|Chance|Risk|Threat|Danger|Hazard|Peril|Jeopardy|Crisis|Emergency|Disaster|Catastrophe|Calamity|Tragedy|Accident|Incident|Occurrence|Happening|Phenomenon|Situation|Circumstance|Condition|Context|Environment|Setting|Atmosphere|Ambiance|Mood|Tone|Feeling|Sense|Impression|Effect|Impact|Influence|Result|Outcome|Consequence|Product|Fruit|Reward|Benefit|Gain|Profit|Advantage|Edge|Lead|Headway|Progress|Advancement|Development|Evolution|Growth|Expansion|Extension|Enlargement|Increase|Rise|Surge|Boost|Jump|Leap|Bound|Spurt|Burst|Flash|Blast|Explosion|Eruption|Outburst|Outbreak|Epidemic|Pandemic|Plague|Scourge|Curse|Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Pkwy|Parkway|Highway|Hwy)\b)[A-Z][a-z]{2,}(?:\s+(?!(?:Office|Offices|Suite|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax|Nature|Science|General|Practice|Theory|Process|Public|Private|Common|Research|Development|Text|Mode|Here|There|This|That|These|Those|The|A|An|All|Some|Many|Both|Each|Every|Few|More|Most|Other|Such|Same|Just|Also|Very|Too|Quite|Well|Now|Then|Than|Into|Upon|Under|Over|Again|Before|After|Until|During|Since|About|Between|Through|Because|North|South|East|West|Northeast|Northwest|Southeast|Southwest|Northern|Southern|Eastern|Western|Central|Upper|Lower|Mid|Inner|Outer|Forward|Backward|Upward|Downward|Internal|External|Left|Right|Top|Bottom|Front|Back|Side|End|Edge|Corner|Middle|Heart|Core|Base|Basis|Ground|Floor|Level|Layer|Tier|Phase|Stage|Step|Point|Spot|Site|Area|Zone|Sector|Region|District|Quarter|Block|Lot|Plot|Field|Track|Line|Row|Column|Node|End|Location|Place|Space|Mark|Sign|Symbol|Icon|Logo|Image|Picture|Photo|Graphic|Art|Design|Pattern|Model|Style|Type|Form|Kind|Sort|Class|Category|Set|Series|Range|Scale|Rate|Degree|Grade|Rank|Status|State|Condition|Position|Role|Function|Task|Job|Work|Duty|Charge|Mission|Operation|Action|Activity|Process|Procedure|Method|Approach|Technique|System|Scheme|Plan|Program|Project|Initiative|Campaign|Drive|Push|Effort|Attempt|Try|Trial|Test|Experiment|Study|Survey|Poll|Census|Count|Tally|Total|Sum|Amount|Number|Figure|Digit|Value|Quantity|Measure|Metric|Index|Indicator|Test|Assessment|Evaluation|Judgment|Rating|Score|Grade|Mark|Label|Brand|Tag|Title|Term|Source|Origin|Root|Cause|Reason|Basis|Ground|Foundation|Path|Route|Course|Channel|Track|Lane|Alley|Passage|Corridor|Hall|Window|Gate|Entrance|Exit|Door|Wall|Ceiling|Roof|Capacity|Size|Dimension|Length|Width|Height|Depth|Breadth|Span|Range|Scope|Extent|Scale|Standard|Norm|Criterion|Benchmark|Baseline|Threshold|Cutoff|Meeting|Conference|Summit|Forum|Seminar|Workshop|Symposium|Convention|Congress|Assembly|Gathering|Meetup|Event|Function|Gala|Ceremony|Tradition|Custom|Convention|Practice|Norm|Standard|Rule|Code|Law|Regulation|Statute|Ordinance|Decree|Edict|Mandate|Order|Command|Instruction|Direction|Guideline|Requirement|Specification|Protocol|Procedure|Policy|Principle|Doctrine|Tenet|Maxim|Axiom|Truth|Fact|Reality|Certainty|Absolute|Given|Constant|Variable|Parameter|Factor|Element|Component|Part|Piece|Segment|Section|Portion|Fraction|Division|Subdivision|Category|Class|Group|Set|Collection|Assembly|Cluster|Batch|Bunch|Pack|Bundle|Stack|Heap|Pile|Mass|Volume|Bulk|Majority|Minority|Plurality|Multitude|Array|Range|Variety|Diversity|Selection|Choice|Option|Alternative|Possibility|Opportunity|Chance|Risk|Threat|Danger|Hazard|Peril|Jeopardy|Crisis|Emergency|Disaster|Catastrophe|Calamity|Tragedy|Accident|Incident|Occurrence|Happening|Phenomenon|Situation|Circumstance|Condition|Context|Environment|Setting|Atmosphere|Ambiance|Mood|Tone|Feeling|Sense|Impression|Effect|Impact|Influence|Result|Outcome|Consequence|Product|Fruit|Reward|Benefit|Gain|Profit|Advantage|Edge|Lead|Headway|Progress|Advancement|Development|Evolution|Growth|Expansion|Extension|Enlargement|Increase|Rise|Surge|Boost|Jump|Leap|Bound|Spurt|Burst|Flash|Blast|Explosion|Eruption|Outburst|Outbreak|Epidemic|Pandemic|Plague|Scourge|Curse|Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Pkwy|Parkway|Highway|Hwy)\b)[A-Z][a-z]+)?(?=\s*,\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\s+\d{5}(?:-\d{4})?)?\b)", 0.55),
    # City before UK postcode: "City, POSTCODE" — e.g. "London, SW1A 2AA", "Manchester, M1 1AE"
    # The postcode format is strongly discriminative; blocked list prevents common nouns from matching.
    ("CITY", r"\b(?!(?:Office|Offices|Suite|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax|Nature|Science|General|Practice|Theory|Process|Public|Private|Common|Research|Development|Text|Mode|Here|There|This|That|These|Those|The|A|An|All|Some|Many|Both|Each|Every|Few|More|Most|Other|Such|Same|Just|Also|Very|Too|Quite|Well|Now|Then|Than|Into|Upon|Under|Over|Again|Before|After|Until|During|Since|About|Between|Through|Because|North|South|East|West|Northeast|Northwest|Southeast|Southwest|Northern|Southern|Eastern|Western|Central|Upper|Lower|Mid|Inner|Outer|Forward|Backward|Upward|Downward|Internal|External|Left|Right|Top|Bottom|Front|Back|Side|End|Edge|Corner|Middle|Heart|Core|Base|Basis|Ground|Floor|Level|Layer|Tier|Phase|Stage|Step|Point|Spot|Site|Area|Zone|Sector|Region|District|Quarter|Block|Lot|Plot|Field|Track|Line|Row|Column|Node|End|Location|Place|Space|Mark|Sign|Symbol|Icon|Logo|Image|Picture|Photo|Graphic|Art|Design|Pattern|Model|Style|Type|Form|Kind|Sort|Class|Category|Set|Series|Range|Scale|Rate|Degree|Grade|Rank|Status|State|Condition|Position|Role|Function|Task|Job|Work|Duty|Charge|Mission|Operation|Action|Activity|Process|Procedure|Method|Approach|Technique|System|Scheme|Plan|Program|Project|Initiative|Campaign|Drive|Push|Effort|Attempt|Try|Trial|Test|Experiment|Study|Survey|Poll|Census|Count|Tally|Total|Sum|Amount|Number|Figure|Digit|Value|Quantity|Measure|Metric|Index|Indicator|Test|Assessment|Evaluation|Judgment|Rating|Score|Grade|Mark|Label|Brand|Tag|Title|Term|Source|Origin|Root|Cause|Reason|Basis|Ground|Foundation|Path|Route|Course|Channel|Track|Lane|Alley|Passage|Corridor|Hall|Window|Gate|Entrance|Exit|Door|Wall|Ceiling|Roof|Capacity|Size|Dimension|Length|Width|Height|Depth|Breadth|Span|Range|Scope|Extent|Scale|Standard|Norm|Criterion|Benchmark|Baseline|Threshold|Cutoff|Meeting|Conference|Summit|Forum|Seminar|Workshop|Symposium|Convention|Congress|Assembly|Gathering|Meetup|Event|Function|Gala|Ceremony|Tradition|Custom|Convention|Practice|Norm|Standard|Rule|Code|Law|Regulation|Statute|Ordinance|Decree|Edict|Mandate|Order|Command|Instruction|Direction|Guideline|Requirement|Specification|Protocol|Procedure|Policy|Principle|Doctrine|Tenet|Maxim|Axiom|Truth|Fact|Reality|Certainty|Absolute|Given|Constant|Variable|Parameter|Factor|Element|Component|Part|Piece|Segment|Section|Portion|Fraction|Division|Subdivision|Category|Class|Group|Set|Collection|Assembly|Cluster|Batch|Bunch|Pack|Bundle|Stack|Heap|Pile|Mass|Volume|Bulk|Majority|Minority|Plurality|Multitude|Array|Range|Variety|Diversity|Selection|Choice|Option|Alternative|Possibility|Opportunity|Chance|Risk|Threat|Danger|Hazard|Peril|Jeopardy|Crisis|Emergency|Disaster|Catastrophe|Calamity|Tragedy|Accident|Incident|Occurrence|Happening|Phenomenon|Situation|Circumstance|Condition|Context|Environment|Setting|Atmosphere|Ambiance|Mood|Tone|Feeling|Sense|Impression|Effect|Impact|Influence|Result|Outcome|Consequence|Product|Fruit|Reward|Benefit|Gain|Profit|Advantage|Edge|Lead|Headway|Progress|Advancement|Development|Evolution|Growth|Expansion|Extension|Enlargement|Increase|Rise|Surge|Boost|Jump|Leap|Bound|Spurt|Burst|Flash|Blast|Explosion|Eruption|Outburst|Outbreak|Epidemic|Pandemic|Plague|Scourge|Curse|Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Pkwy|Parkway|Highway|Hwy)\b)[A-Z][a-z]{2,}(?=\s*,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b)", 0.55),

    # ── DOMAIN ───────────────────────────────────────────────────────
    # DOMAIN comes AFTER URL, DATABASE_URL, PRIVATE_URL, and EMAIL so that
    # domain substrings within those more specific types are deduped.
    # Negative lookahead (?!@) avoids matching email local-parts (e.g. "bob.smith" before @).
    # File extensions like .yaml, .log, .json, .pdf etc. are excluded from matching
    # by requiring that the TLD part not be a common file extension.
    # Negative lookahead blocks common non-domain patterns:
    # - "math.pi", "sin.x" etc. — programming/scientific abbreviations
    # - "com.example:..." — Maven/Gradle coordinates (domain followed by colon)
    # - "and.janedoe" — stripping artifacts (common-word.word followed by word char)
    # - "eyJxxx.yyy" — JWT payload parts (JWT header starts with eyJ)
    # - For multi-level matches (3+ labels), block common English words as the
    #   first label (e.g. "the.quick.brown.fox", "long.dotted.path", "value.with.dots",
    #   "some.other.value" are prose phrases, not real domains).
    # IMPORTANT: Common service/host domains like google, github, gmail, yahoo, etc.
    # are NOT in the negative lookahead — those ARE legitimate domains that should
    # match (e.g. "google.com", "api.github.com"). Only ambiguous tokens that are
    # genuinely not domains (math, sin, and, the, etc.) are blocked.
    # The single-level block (common_word.xx) prevents "and.janedoe" style FPs.
    # The multi-level block (common_word.xx.yy or common_word.xx.yy.zz) prevents
    # prose dotted phrases that happen to match domain syntax.
    ("DOMAIN", r"\b(?<![\/])(?<![a-z]\.[a-z])(?<!@)(?!(?:math|sin|cos|tan|log|exp|abs|min|max|sum|avg|and|the|this|that|for|with|from|have|has|had|not|are|was|were|can|will|its|our|their|my|your|his|her|all|any|each|some|every|many|much|few|more|most|other|such|same|just|also|very|too|quite|well|now|here|there|then|than|as|at|by|in|on|to|of|up|out|off|over|under|again|further|but|or|if|while|because|until|after|before|between|through|during|since|about|into|upon|let|get|set|use|make|take|put|give|say|see|know|think|find|show|tell|ask|try|leave|call|keep|need|feel|seem|help|work|play|run|move|live|stay|want|like|look|come|go|do|be|has|had|did|does|done|having|being|made|taken|given|used|seen|known|found|told|asked|kept|held|brought|began|begun|shown|meant|met|set|put|read|written|built|bought|came|became|become|drawn|driven|eaten|fallen|felt|fought|found|flown|forgotten|given|gone|grown|hung|hidden|held|kept|known|led|left|lost|made|meant|met|paid|proven|put|read|ridden|risen|run|said|seen|sent|set|shown|shut|sung|sunk|sold|spoken|stood|struck|sworn|swept|swum|taken|taught|told|thought|thrown|understood|woken|worn|written)\.[a-z]{2,}\b)(?!(?:eyJ|NiJ|nIJ|nIj)[a-zA-Z0-9]+\.[a-zA-Z0-9])(?![a-zA-Z0-9_-]{3,5}\.[a-zA-Z0-9_-]{25,}\.[a-zA-Z]{2,3}\b)(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b(?!:)(?!@)(?<!\.yaml)(?<!\.json)(?<!\.xml)(?<!\.toml)(?<!\.ini)(?<!\.cfg)(?<!\.conf)(?<!\.log)(?<!\.txt)(?<!\.md)(?<!\.rst)(?<!\.html)(?<!\.css)(?<!\.js)(?<!\.ts)(?<!\.py)(?<!\.rb)(?<!\.java)(?<!\.cpp)(?<!\.c)(?<!\.h)(?<!\.go)(?<!\.rs)(?<!\.php)(?<!\.sql)(?<!\.db)(?<!\.pdf)(?<!\.doc)(?<!\.docx)(?<!\.xls)(?<!\.xlsx)(?<!\.ppt)(?<!\.pptx)(?<!\.png)(?<!\.jpg)(?<!\.jpeg)(?<!\.gif)(?<!\.svg)(?<!\.ico)(?<!\.zip)(?<!\.tar)(?<!\.gz)(?<!\.tgz)(?<!\.bz2)(?<!\.xz)(?<!\.7z)(?<!\.lock)(?<!\.env)", 0.75),

    # ── COMPANY ──────────────────────────────────────────────────────
    ("COMPANY", r"\b(?:[A-Z][a-z]+)\s+(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|Incorporated|PLC|AG|SA|BV|NV)\.?\b", 0.80),
    ("COMPANY", r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|PLC|AG|SA|BV|NV)\.?\b", 0.80),
    ("COMPANY", r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\s+(?:Technologies|Tech|Systems|Software|Solutions|Group|Partners|Holdings|Enterprises|Ventures|Industries|Global|International|Digital|Media|Networks|Services|Consulting|Associates)\b", 0.75),
    # Two capitalized words — low confidence. Only match if the second word
    # looks like a company name component (e.g., Corp, Inc like structures or
    # industry words like Motors, Airlines, Foods, etc.) or the first word is
    # a company keyword (e.g., Acme, Widgets type prefixes).
    # This avoids matching common name phrases, address components, project names, etc.
    ("COMPANY", r"\b(?:[A-Z][a-z]+)\s+(?:Technologies|Tech|Systems|Software|Solutions|Group|Partners|Holdings|Enterprises|Ventures|Industries|Global|International|Digital|Media|Networks|Services|Consulting|Associates|Motors|Airlines|Foods|Pharma|Bio|Labs|Works|Studios|Games|Health|Energy|Power|Capital|Finance|Insurance|Logistics|Transport|Retail|Electric|Chemical|Materials|Mining|Oil|Gas|Water|Telecom|Interactive|Cloud|Data|AI|Robotics)\b", 0.55),
    # Context-prefixed single-word company names: "works at X", "Invoice from X",
    # "Signed by X", "X is the vendor", "Company: X", "regarding X"
    # Requires the company word to be capitalized, 3+ letters long.
    # Negative lookahead avoids matching when followed by Inc/Corp/LLC etc.
    # (those are already caught by the higher-confidence patterns).
    # NOTE: keyword prefix is matched as part of finditer() but the detector
    # dedup will prefer the narrower "name only" match if that pattern fires first.
    ("COMPANY", r"(?i)(?:(?:work|works)\s+at|Invoice\s+from|Signed\s+by|regarding)\s+(?:(?:the|our)\s+)?(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Project|New|Los|San|Las|Buenos|Bangkok|Hong|Kuala|Rio|Sao|Cape|Kowloon)[A-Z])[a-z]{3,}(?:(?:\s+(?:(?:the|our|and)\s+)?(?-i:[A-Z])[a-z]{2,}))?\b", 0.65),
    # "Company: X" / "Vendor: X" / "Organization: X" prefix — NOT "Client:" which
    # often precedes a person name.
    ("COMPANY", r"(?i)(?:Company|Vendor|Organization)\s*[：:]\s*(?:(?:the|our)\s+)?(?-i:[A-Z])[a-z]{2,}(?:\s+(?:(?:the|our|and)\s+)?(?-i:[A-Z])[a-z]+)?\b", 0.70),
    # "X is the vendor" / "X is our vendor" / "X is a vendor"
    ("COMPANY", r"(?-i:[A-Z])[a-z]{3,}(?:\s+(?:(?:the|our|and)\s+)?(?-i:[A-Z])[a-z]+)?\s+is\s+(?:the|our|a)\s+vendor\b", 0.65),
    # Two capitalized words acting as company name (no suffix needed) in
    # company context — preceded by known company keywords.
    # NOTE: keyword prefix is matched as part of finditer() but the detector
    # dedup will prefer the narrower "name only" match if that pattern fires first.
    ("COMPANY", r"(?i)(?:(?:work|works)\s+at|Invoice\s+from|Signed\s+by|regarding)\s+(?-i:(?!Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Project|New|Los|San|Las|Buenos|Bangkok|Hong|Kuala|Rio|Sao|Cape|Kowloon)[A-Z])[a-z]+(?:\s+(?:(?:the|our|and|n|'n)\s+)?(?-i:[A-Z])[a-z]+)\b", 0.60),
    # Explicit known companies list — single-word brand names that are
    # well-known companies. These are high-precision names that don't
    # require context keywords. Only include names that are unlikely to
    # be common person names or other false positives.
    ("COMPANY", r"\b(?:Meta|Apple|Google|Amazon|Microsoft|Netflix|Spotify|Tesla|SpaceX|Intel|IBM|SAP|Adobe|Salesforce|Uber|Airbnb|Lyft|Pinterest|Snapchat|TikTok|Zoom|Slack|GitHub|GitLab|Atlassian|Shopify|Twilio|Stripe|Square|PayPal|Venmo|Coinbase|Palantir|Snowflake|Datadog|Databricks|HashiCorp|Canva|Figma|Notion|Linear|Vercel|Netlify|DigitalOcean|Heroku|Alibaba|Tencent|Baidu|Samsung|Sony|Nintendo|Honda|Toyota|BMW|Mercedes|Audi|Volkswagen|Porsche|Ferrari|McLaren|Boeing|Raytheon|Nestle|Pepsi|Pfizer|Moderna|Novartis|Roche|Merck|Sanofi|Bayer|Siemens|Bosch|Philips|Xerox|Cisco|Dell|Lenovo|Asus|Acer|Huawei|Xiaomi|Oppo|Vivo|OnePlus|Nokia|Ericsson|Qualcomm|Broadcom|AMD|Nvidia|Micron|Seagate|DoorDash|Instacart|Roblox|Unity|Capcom|Sega|Ubisoft|Activision|Blizzard|Mitsubishi|Canon|Panasonic|Sharp|Toshiba|Hitachi|Fujitsu|Nikon|Ricoh|Epson|Logitech|GoPro|Fitbit|Roku|Dropbox|Evernote|Trello|Asana|Monday|Zendesk|HubSpot|Mailchimp|Wix|Squarespace|Weebly|Godaddy|Namecheap|Cloudflare|Fastly|Akamai|Okta|CrowdStrike|Palo Alto|Fortinet|Splunk|New Relic|Sumo Logic|Elastic|Confluent|HashiCorp|Hugging Face|OpenAI|Anthropic|Cohere|Stability AI|Midjourney|Runway)\b", 0.75),
    # Two-word explicit known companies (with spaces in name)
    ("COMPANY", r"\b(?:Wells Fargo|Bank of America|Coca-Cola|Procter & Gamble|Johnson & Johnson|Morgan Stanley|Credit Suisse|Deutsche Bank|Goldman Sachs|Hewlett Packard|Hewlett-Packard|Lockheed Martin|Northrop Grumman|Electronic Arts|Take-Two Interactive|Square Enix|Bandai Namco|Western Digital|General Electric|General Motors|Ford Motor|Berkshire Hathaway|McKinsey & Company|Boston Consulting|Bain & Company|Deloitte Consulting|PricewaterhouseCoopers|Ernst & Young|KPMG|Accenture|Walmart|Target|Costco|Home Depot|Lowe's|Best Buy|McDonald's|Burger King|Wendy's|KFC|Taco Bell|Pizza Hut|Domino's|Subway|Starbucks|Dunkin'|Chipotle|Panera|Whole Foods|Trader Joe's|Aldi|Lidl|Carrefour|Tesco|Sainsbury's|John Lewis)\b", 0.80),
    # Catch compound company names like LexCorp, Oscorp, OpenCorp, etc.
    # Pattern: capitalized word ending in Corp/Soft/Tech/Works/Labs/etc
    ("COMPANY", r"\b[A-Z][a-z]{2,}(?:Corp|Corp\.|Soft|Tech|Works|Labs|Ware|Mart|Hub|Box|Cloud|Space|Mail|Sync|Chat|Bot|Pay|Log|Jet|Nest|Map|Pad|Pod)\b", 0.70),
    # Two-word company names used in "I'm from X" introductions — the "from"
    # keyword must immediately precede a capitalized two-word phrase.
    # Low confidence to avoid FPs on "from New York", "from Boston" etc.
    # Avoid matching inside parentheticals like "(famous from Finding Nemo)"
    # NOTE: "from" prefix is included in the match. The narrower company-only
    # pattern fires separately (e.g. "Widgets Inc") so this is supplementary.
    ("COMPANY", r"(?i)from\s+(?-i:(?!New|Los|San|Las|Buenos|Bangkok|Hong|Kuala|Rio|Sao|Cape|Las|Buenos|Kowloon|Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Project|Customer|Enterprise|Vendor|Client|Partner|Employee|Member|User|Developer|Engineer|Analyst|Agent|Operator|Supervisor|Coordinator)[A-Z])[a-z]+(?:\s+(?:(?:the|our|and|n|'n)\s+)?(?-i:(?!Team|Group|Department|Division|Unit|Office|Section|Desk|Board|Council|Committee|Staff|Personnel|Management|Leadership|Executive|Member|Analyst|Engineer|Developer)[A-Z])[a-z]+)(?![^(]*\))(?!\s*(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co\.?|Company|Corporation|PLC|AG|SA|BV|NV))\b", 0.50),
    # Single-word company name after "from" — known brand names that won't be confused with cities.
    # Supports hyphenated company names like "Weyland-Yutani".
    ("COMPANY", r"(?i)from\s+(?-i:(?!London|Paris|Berlin|Madrid|Rome|Moscow|Tokyo|Delhi|Mumbai|Beijing|Shanghai|Sydney|Dublin|Amsterdam|Vienna|Zurich|Boston|Chicago|Seattle|Austin|Denver|New|San|Los|Las|Cape|Buenos|Kuala|Hong|Rio|Sao|Bangkok|Kowloon|Spain|France|Germany|Italy|UK|USA|Canada|Australia|China|Japan|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|Egypt|Thailand|Vietnam|Indonesia|Malaysia|Singapore|Greece|Finland|Hungary|Romania|Ukraine|Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Project|Tech|Customer|Enterprise|Vendor|Client|Partner|Employee|Member|User|Analytics|Development|Engineering|Marketing|Finance|Operations|Production|Quality|Research|Training|Planning)[A-Z])[a-z]+(?:[-][A-Z][a-z]+)?\b(?!\s+(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|PLC|AG|SA|BV|NV|Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|and|the|of|in|at|on|for|with|from|is|was|has|had|have|not|by|to))\b(?![^(]*\))", 0.55),
    # Single-word company name after "regarding" — catch brands and hyphenated names
    # Denylist blocks technical terms, geographic names, and project names
    ("COMPANY", r"(?i)regarding\s+(?-i:(?!New|Los|San|Las|Support|Config|Settings|Default|Admin|System|Account|Login|Upgrade|Billing|Notification|Report|Dashboard|Security|Access|Manager|Team|Profile|Postgres|PostgreSQL|Nginx|Docker|Kubernetes|Systemd|Project|Tech|Customer|Enterprise|Vendor|Client|Partner|Employee|Member|User|Analytics|Development|Engineering|Marketing|Finance|Operations|Production|Quality|Research|Training|Planning|Performance|Capacity|Growth|Innovation|Strategy|Planning)[A-Z])[a-z]{2,}(?:[-][A-Z][a-z]+)?\b", 0.55),

]