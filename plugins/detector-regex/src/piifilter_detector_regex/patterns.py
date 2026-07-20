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

    # ── PRIVATE_URL ──────────────────────────────────────────────────
    ("PRIVATE_URL", r"\bhttps?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\bhttps?://[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.[\w-]+)*(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\b[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.[\w-]+)*(?::\d+)(?:/[^\s]*)?\b", 0.85),
    # Bare internal hostname (no dot): http://internal:80/path
    ("PRIVATE_URL", r"\bhttps?://(?:internal|localhost|db|api|app|backend|frontend|redis|postgres|mysql|rabbitmq)(?::\d+)?(?:/[^\s]*)?\b", 0.80),

    # ── URL ──────────────────────────────────────────────────────────
    # Full http/https URLs
    ("URL", r"\bhttps?://[\w./?=&%-]+(?:\.[\w./?=&%-]+)*\b", 0.85),
    # www. prefixed URLs without protocol
    ("URL", r"\bwww\.[\w./?=&%-]+\.[\w]{2,}(?:/[\w./?=&%-]*)?\b", 0.80),

    # ── JWT ──────────────────────────────────────────────────────────
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b", 0.95),
    # Truncated JWT (two parts, common in abbreviated context)
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.\.\.\w*\b", 0.90),
    ("JWT", r"\beyJ[a-zA-Z0-9_-]{3,20}\.\.[a-zA-Z0-9_-]{3,10}\b", 0.85),
    # JWT with 3 dots as ellipsis: "eyJzdW...IyfQ"
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.\.\.[a-zA-Z0-9_-]+\b", 0.85),
    # JWT that is essentially a base64 encoded payload (single segment, no dots)
    ("JWT", r"\beyJ[a-zA-Z0-9+/=_-]{20,}\b", 0.70),

    # ── DATABASE_URL ─────────────────────────────────────────────────
    ("DATABASE_URL", r"\b(?:postgresql|postgres|mysql|mongodb|redis|sqlite|oracle|mssql)://\S+", 0.95),

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
    ("SOCIAL_SECURITY", r"[X*#]{3}[- ][X*#]{2}[- ]\d{4}", 0.70),
    # Same with bullet characters (U+2022, U+25CF): •••-••-9074
    ("SOCIAL_SECURITY", r"[\u2022\u25CF]{3}[- ][\u2022\u25CF]{2}[- ]\d{4}", 0.70),
    # Context-prefixed X-masked SSN: "SSN 9XX-XX-4321", "SSN 1XX-XX-6789" — first digit real, positions 2-5 masked
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|ss#)\s+\d[X*#]{2}[- ][X*#]{2}[- ]\d{4}\b", 0.70),
    # Full mask with context: "SSN XXX-XX-XXXX"
    ("SOCIAL_SECURITY", r"(?i)\b(?:ssn|social security|ss#)\s+[X*#]{3}[- ]{2,4}\d{4}\b", 0.65),
    # Context-based masked SSN: "masked SSN: XXX-XX-9074"
    ("SOCIAL_SECURITY", r"(?i)(?:mask|redact|obfuscat)[a-z]*\s*(?:social|ssn|ss#)\s*:?\s*[X*#]{3}[- ]\d{2}[- ]\d{4}\b", 0.60),
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

    # ── IBAN ─────────────────────────────────────────────────────────
    # IBAN must come BEFORE CREDIT_CARD patterns since IBAN substrings (like
        # "6016 1331 9268 19") can look like credit card numbers. The dedup logic
    # skips detections contained within already-matched intervals.
    ("IBAN", r"\b[A-Z]{2}\d{2}(?:[ ]?(?:[A-Z0-9]{4})){4,7}(?:[ ]?\d{1,4})?\b", 0.85),
    # Shorter IBAN variants: NL91 ABNA 0417 1643 00, DK50 0040 0440 1162 43, NO93 8601 1117 947
    ("IBAN", r"\b[A-Z]{2}\d{2}\s+[A-Z]{4}\s+\d{4}\s+\d{4}\s+\d{2,4}(?:\s+\d{1,3})?\b", 0.85),

    # ── CREDIT_CARD ──────────────────────────────────────────────────
    # Masked/bullet CC — partial redaction with last-4 visible: XXXX-XXXX-XXXX-1234, ****-****-****-5678
    ("CREDIT_CARD", r"(?:[X*#]{4}[- ]){3}\d{4}\b", 0.70),
    # Same with bullet characters (U+2022, U+25CF): ••••-••••-••••-1111
    ("CREDIT_CARD", r"(?:[\u2022\u25CF]{4}[- ]){3}\d{4}\b", 0.70),
    # Context-prefixed masked CC: "Credit card: XXXX-XXXX-XXXX-1234"
    ("CREDIT_CARD", r"(?i)(?:credit\s*card|cc|card)\s*:?\s*(?:number\s+)?(?:is\s+)?(?:[X*#]{4}[- ]){3}\d{4}\b", 0.65),
    # Context-based masked reference: "masked card: ****-****-****-0004"
    ("CREDIT_CARD", r"(?i)(?:mask|redact|obfuscat|hidden)[a-z]*\s*(?:credit|cc|card)\s*:?\s*(?:[X*#]{4}[- ]){3}\d{4}\b", 0.60),
    ("CREDIT_CARD", r"(?i)\b(?:credit\s*card|cc|card)\s*(?:number|no|#)?\s*:?\s*\d[ -]*?\d{13,18}\b", 0.90),
    # Standard 4-4-4-4 format with single dashes or single spaces
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b(?![ -]\d{2,4})", 0.85),
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
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)\b\d{4}[ .-]+\d{4}[ .-]+\d{4}[ .-]+\d{2,4}\b", 0.65),
    # Low confidence: 4-4-4-2..4 pattern with single dash/space
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)(?<![A-Za-z])(?<!\d{4}[- ])\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{2,4}\b(?![- ]\d{2,4})(?!\s*\d{2,4})", 0.65),
    # Low confidence: 4-4-4-2..4 with multi-space gaps (e.g. "3782  8224  6310  005")
    ("CREDIT_CARD", r"\b\d{4}[ -]{2,}\d{4}[ -]{2,}\d{4}[ -]{2,}\d{2,4}\b", 0.65),
    # Continuous 16-digit credit card numbers (no dashes) — keyword-prefixed
    ("CREDIT_CARD", r"(?i)(?:credit\s*card|cc|card\s+#?)\b\s*\d{16}\b", 0.80),
    # IIN-prefixed 16-digit numbers: known card issuer prefixes
    ("CREDIT_CARD", r"\b(?:4\d{3}|5[1-5]\d{2}|6\d{3}|3[47]\d{2})\d{12}\b", 0.80),
    # Generic 16-digit number — low confidence (Luhn gate filters FPs).
    ("CREDIT_CARD", r"\b\d{16}\b", 0.50),
    # Catch-all for continuous 13-19 digit numbers that are Luhn-valid.
    # Lower confidence since no format hint — relies on Luhn gate.
    ("CREDIT_CARD", r"\b\d{13,19}\b", 0.65),

    # ── EMAIL ────────────────────────────────────────────────────────
    # Local part: word chars, dots, +, -, *, percent-encoded chars, quotable specials
    # Domain: word chars and hyphens (no underscore for domain)
    # TLD: word chars, dots and hyphens (for multi-level TLDs like .co.uk)
    ("EMAIL", r"\b[\w.+*-]+@[\w-]+\.[\w.-]+\b", 0.90),
    # Catch star-obfuscated emails where only * and first/last letter remains
    # e.g. j**n@example.com, s***t@company.com — pattern above catches these now
    # but this lower-confidence fallback catches edge cases with longer stars
    ("EMAIL", r"\b[\w.*]{2,}@[\w.-]+\.[\w.-]+\b", 0.85),

    # ── API_KEY ──────────────────────────────────────────────────────
    ("API_KEY", r"\b(?:sk-|pk-|api[-_]?key|token|secret)[-_]?[a-zA-Z0-9_\-]{16,64}\b", 0.95),
    ("API_KEY", r"\b(?:[A-Za-z0-9+/=]{20,})\b(?=.*(?:key|token|secret))", 0.90),

    # ── PHONE ────────────────────────────────────────────────────────
        # Unicode dash character class: hyphen-minus, en-dash, em-dash, minus sign
        # Keyword-prefixed phone numbers (phone/tel/mobile/cell/call + number)
        # Must have at least 7 digits to avoid matching short sequences.
        # Negative lookahead avoids matching credit card numbers (4 groups of 4+ digits).
        ("PHONE", r"(?i)\b(?:phone|tel|telephone|mobile|cell|call)\s*(?:number|no|#)?\s*\-?\s*(?!\d{4,}[–—−\-.\s]\d{4,}[–—−\-.\s]\d{4,})\+?[\d\(][\d\s\-\.\(\)]{7,20}\b", 0.90),
        # International with + and unicode dashes: +1-555-123-4567, +1–555–123–4567, +1—555—123—4567, +1−555−123−4567
        ("PHONE", r"(?:^|\s)\+\d{1,3}[–—−\-. ]\d{2,4}[–—−\-. ]\d{3,4}[–—−\-. ]\d{4}\b", 0.88),
        # International with + and spaces only (variable groupings): +44 20 7946 0958, +1 555 123 4567
        ("PHONE", r"(?:^|\s)\+\d{1,3}(?:\s+\d{2,4}){2,4}\b", 0.85),
        # International with +, country code 1 digit, spaced with optional unicode dashes inside
        ("PHONE", r"(?:^|\s)\+\d\s+\d{3}\s+\d{3}[–—−\-. ]?\d{2}[–—−\-. ]?\d{2}\b", 0.85),
        # International with + and mixed separators (any combo of dash types and spaces)
        ("PHONE", r"(?:^|\s)\+\d{1,3}[–—−\-.]\d{2,4}[–—−\-. ]\d{3,4}[–—−\-. ]?\d{3,4}\b", 0.85),
        # Bare E.164 with + prefix: "+14085551212" style
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
        # Phone numbers after CJK 电话/電話 keywords (with unicode dash support)
        # Supports formats: +86 138-0013-8000, +1-555-123-4567, +81 90-1234-5678
        ("PHONE", r"(?i)(?:电话|電話)\+[\d–—−\-]+(?:[\s–—−\-]+\d[\d–—−\-]*){2,}\b", 0.85),
        # CJK phone: 電話は+X XX-XXXX-XXXX (Japanese context, unicode dash support)
        ("PHONE", r"(?i)(?:電話は|电话是|電話)\s*\+\d+[\s–—−\-]?\d+[\s–—−\-]?\d+[\s–—−\-]?\d+\b", 0.85),
        # German format after Phone: — "+49 30 12345678"
        ("PHONE", r"(?i)\bPhone:\s*\+\d{1,3}\s+\d{2,4}\s+\d{5,10}\b", 0.80),
        # Universal variable-separator pattern: catch-all for phone-like sequences
                # with at least 9 digits and mixed separators (dashes, dots, spaces)
                # Uses negative lookahead to avoid matching:
                #   - IP addresses (already covered by IP_ADDRESS patterns)
                #   - Credit card 4-4-4-4 patterns (already covered by CREDIT_CARD)
                #   - IBAN segments (preceded by 2-letter country code)
                #   - Space-separated 4-group IPs like "10 10 10 10", "192 168 1 100"
                ("PHONE", r"(?!\d{1,3}(?:\.\d{1,3}){3}\b)(?!\d{1,3}\s+\d{1,3}\s+\d{1,3}\s+\d{1,3}\b)(?![A-Z]{2}\d)\b\d{2,4}[–—−\-.\\s]\d{2,4}[–—−\-.\\s]\d{2,4}[–—−\-.\\s]?\d{2,4}\b(?![–—−\-.\\s]?\d{2,4})", 0.55),

    # ── IP_ADDRESS ───────────────────────────────────────────────────
    # Standard dotted-decimal IPv4 with strict octet validation (0-255 per octet).
    # Uses negative lookbehind/lookahead to avoid matching IP-like substrings
    # inside dates (e.g. "12.31.2025" where month=12 day=31 would match as IP).
    # Blocks: octet > 255, leading zeros that would imply octal.
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b", 0.90),
    # Full IPv6 (7 colons, 8 groups): 2001:0db8:85a3:0000:0000:8a2e:0370:7334
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.88),
    # IPv6 with single :: anywhere
    ("IP_ADDRESS", r"\b(?:(?:[0-9a-fA-F]{1,4}:){1,7}:|:(?::[0-9a-fA-F]{1,4}){1,7})\b", 0.88),
    # IPv6 loopback: ::1
        ("IP_ADDRESS", r"(?:(?<=\s)|(?<=\A)|(?<=:))::1(?:(?=\s)|(?=\Z))", 0.90),
        # IPv6 unspecified: ::
        ("IP_ADDRESS", r"(?:(?<=\s)|(?<=\A))::(?:(?=\s)|(?=\Z))", 0.85),
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
    # Individual numbers that are clearly coordinates (1-3 digit integer part, 2+ decimal places)
    # Catches longitudes like -122.4194 and values like 52.52 or 13.405 with fewer decimals
    # Excludes IP address fragments (e.g. "192.168" in "192.168.1.1") and prices ("$3.50")
    ("GPS", r"(?<!\d)(?<!\d\.)(?<!\$)[-+]?\d{1,3}\.\d{2,}(?!\.\d)(?!\d)", 0.70),

    # ── FILE_PATH ────────────────────────────────────────────────────
    ("FILE_PATH", r"(?<!\/)/(?:[a-zA-Z0-9._-]+/){3,}[a-zA-Z0-9._-]*(?!\w)", 0.85),
    ("FILE_PATH", r"(?<!\/)/(?:home|var|etc|usr|opt|tmp|root|mnt|media|run|srv)/(?:[a-zA-Z0-9._-]+/?)+[a-zA-Z0-9._-]+(?!\w)", 0.90),
    ("FILE_PATH", r"(?<!\w)(?:[A-Za-z]:\\[a-zA-Z0-9._\\ -]+)(?!\w)", 0.90),

    # ── DOMAIN ───────────────────────────────────────────────────────
    # Negative lookahead (?!@) avoids matching email local-parts (e.g. "bob.smith" before @).
    # File extensions like .yaml, .log, .json, .pdf etc. are excluded from matching
    # by requiring that the TLD part not be a common file extension.
    ("DOMAIN", r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b(?!@)(?<!\.yaml)(?<!\.json)(?<!\.xml)(?<!\.toml)(?<!\.ini)(?<!\.cfg)(?<!\.conf)(?<!\.log)(?<!\.txt)(?<!\.md)(?<!\.rst)(?<!\.html)(?<!\.css)(?<!\.js)(?<!\.ts)(?<!\.py)(?<!\.rb)(?<!\.java)(?<!\.cpp)(?<!\.c)(?<!\.h)(?<!\.go)(?<!\.rs)(?<!\.php)(?<!\.sql)(?<!\.db)(?<!\.pdf)(?<!\.doc)(?<!\.docx)(?<!\.xls)(?<!\.xlsx)(?<!\.ppt)(?<!\.pptx)(?<!\.png)(?<!\.jpg)(?<!\.jpeg)(?<!\.gif)(?<!\.svg)(?<!\.ico)(?<!\.zip)(?<!\.tar)(?<!\.gz)(?<!\.tgz)(?<!\.bz2)(?<!\.xz)(?<!\.7z)(?<!\.lock)(?<!\.env)", 0.75),

    # ── PASSPORT ─────────────────────────────────────────────────────
    ("PASSPORT", r"(?i)(?:^|\s)(?:passport)\s*(?:number|no|#)?\s*:?\s*[A-Z]{0,2}\d{6,9}\b", 0.85),
    ("PASSPORT", r"\b[A-Z]{1,2}\d{6,9}\b", 0.75),

    # ── BANK_ACCOUNT ─────────────────────────────────────────────────
    ("BANK_ACCOUNT", r"(?i)\b(?:bank|account|acct|A/c)\s*(?:number|no|#)?\s*:?\s*\d{8,17}\b", 0.85),
    # Non-IBAN-looking digit sequences — exclude those starting with 2 letters
    ("BANK_ACCOUNT", r"(?<![A-Za-z])\b\d{12,20}\b", 0.55),

    # ── PERSON ───────────────────────────────────────────────────────
    # Title-prefixed — name must be 2+ chars, not a single letter
    ("PERSON", r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.85),
    # "I'm/My name is/Call me + Name"
    # Require 3+ chars in each name word to avoid single-letter initials or short fragments
    ("PERSON", r"(?i)(?:\bmy name is|\bI'm|\bcall me|\bname is)\s+(?-i:[A-Z])[a-z]{3,}(?:\s+(?-i:[A-Z])[a-z]{3,}){0,2}\b", 0.80),
    # "ROLE + Name" — exclude common role/researcher-type words after the name
    # Require 3+ chars to avoid matching 2-letter initials; lower confidence
    ("PERSON", r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?-i:[A-Z])[a-z]{3,}(?:\s+(?-i:[A-Z])[a-z]{3,})?\b", 0.70),
    # "Person:" prefix — handle titles like Dr., Mr. — require at least one real name word
    # Negative lookahead blocks words like "researcher", "published", "from", "at" that are common role/context words
    # Also blocks common non-person continuations: addresses, company suffixes, job titles
    ("PERSON", r"(?i)\bPerson:\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+)?(?-i:[A-Z])[a-z]{2,}(?:[.']?[a-z]+)?(?:\s+(?-i:[A-Z])[a-z]{2,}(?:[.']?[a-z]+)?){0,1}(?!\s+(?:researcher|published|from|at|in|of|the|a|an|and|or|for|with|by|to|on|is|was|has|had|said|says|who|whom|whose|where|when|what|which|that|this|these|those|Inc|Corp|LLC|Ltd|Limited|GmbH|Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd))(?:[.]?)\b", 0.80),
    # "Contact person:" / "Contact name:"
    ("PERSON", r"(?i)\bContact\s+(?:person|name):\s*(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.80),
    # Unicode/Non-Latin names — matched by context keywords (CJK + common non-Latin alphabet names)
    # CJK: keyword 用户/联系人/姓名 directly followed by name (no colon needed)
    # Exclude common technical terms that look like capitalized names (Postgresql, Admin, Root, etc.)
    # Also exclude company suffixes and address suffixes
    ("PERSON", r"(?i)\b(?:contact|person)\s*[：:]\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+)?[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?(?!\s+(?:researcher|published|from|at|in|of|the|a|an|and|or|for|with|by|to|on|is|was|has|had|said|says|who|whom|whose|where|when|what|which|that|this|these|those|Inc|Corp|LLC|Ltd|Limited|GmbH|Street|St|Avenue|Ave|Road|Rd))\b", 0.75),
    # user: prefix — more restrictive to avoid technical terms like 'user: postgresql'
    # Extended exclusion list for common non-person user labels; require 3+ chars in name
    ("PERSON", r"(?i)\buser\s*[：:](?!\s*(?:admin|root|postgres|postgresql|mysql|default|guest|test|anonymous|nobody|system|api|service|demo|readonly|backup|deploy|ci|cd|bot|monitor|agent|worker|dev|prod|staging|localhost|primary|secondary))\s*[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?\b", 0.65),
    # CJK-specific: 用户/联系人/姓名 directly followed by 2+ CJK characters
    ("PERSON", r"(?:用户|联系人|姓名|名前)[：:]?\s*[\u4e00-\u9fff]{2,4}(?:\s+[\u4e00-\u9fff]{2,4})?\b", 0.80),
    # Russian/Cyrillic names
    ("PERSON", r"(?i)\b(?:contact|user|person|connect|reach)\s+(?:is|name)\s+[\u0400-\u04ff]+\b", 0.75),
    # Arabic script names — handle بـ prefix (U+0628 + optional tatweel U+0640)
    # Exclude standalone بـ without a following name
    ("PERSON", r"(?i)\b(?:اتصل)\s+بـ?\s*[\u0600-\u06ff]{2,}\b", 0.80),
    ("PERSON", r"(?i)\b(?:اسم|اسمي)\s+[\u0600-\u06ff]+\b", 0.80),
    # Japanese: CJK name followed by の (possessive) or さん (honorific)
    ("PERSON", r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,4}(?:の|さん)\b", 0.70),
    # Greek alphabet names (O + name pattern for "O Γιώργος")
    ("PERSON", r"(?i)\bO\s+[\u0370-\u03ff]+\b", 0.70),
    # Any non-Latin name caught by context + multiple non-Latin word chars
    ("PERSON", r"\b(?:name|email|phone|mail|contact|user)\s*[：:]\s*[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff]+\b", 0.65),
    # Non-Latin names after language labels — use lookbehind so match starts at the name
    # Require at least 3+ consecutive non-Latin chars to avoid matching
    # short prefixes that aren't names
    # Exclude Arabic prefix words that aren't names themselves
    ("PERSON", r"(?i)(?:(?<=Russian:)|(?<=Arabic:)|(?<=Japanese:)|(?<=Greek:)|(?<=Unicode))\s*(?-i:[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])[a-z0-9\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{3,}(?:\s+(?-i:[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])[a-z0-9\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]*)?\b", 0.70),

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
    ("PROJECT_NAME", r"(?i)\b(?:project|initiative|campaign|program)\s+(?:name\s+)?(?:is\s+)?(?:called\s+)?(?-i:[A-Z])[a-zA-Z0-9]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)*\b", 0.80),
    ("PROJECT_NAME", r"\b(?:Project|Operation|Initiative|Program|Code[- ]?name)\s+(?-i:[A-Z])[a-zA-Z0-9]+\b", 0.85),
    # Standalone capitalized project names like "Project Phoenix", "Omega Protocol"
    ("PROJECT_NAME", r"\b(?:Project|Operation|Initiative|Program|Task)\s+(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)?\b", 0.80),
    # Two-word capitalized names in project context like "Blue Sky", "Omega Protocol"
    ("PROJECT_NAME", r"(?i)\b(?:working\s+on|assigned\s+to)\s+(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z]+)?\b", 0.70),
    # "X milestone due" pattern
    ("PROJECT_NAME", r"(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\s+milestone\s+due\b", 0.70),
    # "X is in development / in maintenance"
    ("PROJECT_NAME", r"(?i)(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z]+)?\s+is\s+in\s+(?:development|maintenance|maint)\b", 0.65),

    # ── ADDRESS ──────────────────────────────────────────────────────
            # Standard address: "N Street Name St/Rd/Ave/etc."
            # Enhanced: captures street + city + state + ZIP/postcode for full address matching.
            # Uses negative lookbehind (?<!not\s) to block ", not 123 Main St" teaching patterns.
            # Uses a general negative lookahead for parentheticals that look like media references.
            # Optional suffix captures city, state abbreviation + ZIP, or UK postcode after street.
            ("ADDRESS", r"\b(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?:,\s*[A-Z][a-z]+(?:[\s-]+[A-Z][a-z]+)*(?:,\s*(?:[A-Z]{2}\s+\d{5}(?:-\d{4})?|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}|\d{5})))?(?:\s*,\s*[A-Za-z]+(?:\s+[A-Za-z]+)?)?(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:movie|show|film|game|series|cartoon|animation|episode|from\s+[A-Z]))\b", 0.85),
            # European-style addresses: "Street Name N, Postcode City" — where the number comes
        # after the street name, followed by comma and postcode + city.
        # Supports multi-word street names with lowercase particles (den, der, von, etc.)
        # and non-ASCII characters (ü, ß, é, etc.). The first word must start with an
        # uppercase letter to avoid matching generic phrases.
        # Catches patterns like "Unter den Linden 1, 10117 Berlin", "Rue de la Paix 15, 75002 Paris"
    ("ADDRESS", r"\b(?:[A-Z]\w*(?:\s+(?:[A-Z]\w*|den|der|die|das|von|vom|zum|zur|am|im|in|an|auf|bei|mit|und|oder|aus|nicht|dem|des|ein|eine|einer|einem|für|über|unter|und|of|the|la|le|les|de|del|della|dos|das|van|ver|des|du|sur|aux|en|el)){0,5})\s+\d{1,4}[a-z]?,\s*\d{4,5}\s+\w+(?:[\s-]+\w+)?\b", 0.80),
        ("ADDRESS", r"\bP\.?\s*O\.?\s+Box\s+\d+\b", 0.85),
        ("ADDRESS", r"\b(?:Suite|Apt|Unit|Building)\s+#?\d+[A-Za-z]?\b", 0.80),

    # ── CITY ─────────────────────────────────────────────────────────
    ("CITY", r"(?i)\b(?:city|town)\s*(?:of|pop|population)?\s*:?\s*(?!(?:The|A|An|This|That|These|Those|Our|Their|My|Your|His|Her|Its)\b)[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?\b", 0.70),
    # Cities followed by comma + known country — use positive lookahead so match is JUST the city name
    # Exclude country names from the city position to avoid COUNTRY→CITY confusion
    ("CITY", r"\b(?!(?:Canada|Australia|Germany|France|Italy|Spain|Japan|China|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|Egypt|Nigeria|South Africa|Kenya|Thailand|Vietnam|Indonesia|Malaysia|Singapore|New Zealand|Greece|Finland|Hungary|Romania|Ukraine)\b)[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:Germany|France|Italy|Spain|UK|England|USA|US|China|Japan|India|Brazil|Canada|Australia)\b)", 0.70),
    # City after "works at X in City" or "based in City"
        ("CITY", r"(?i)\b(?:based\s+in|works?\s+(?:at\s+\S+\s+)?in|lives?\s+in|located\s+in|situated\s+in)\s+(?-i:[A-Z])[a-z]{2,}\b", 0.60),
        # City after "in" — capture just the city name (no country in match)
        # Require 4+ chars and exclude common non-city capitalized words and backtick-quoted words
        ("CITY", r"(?i)\bin\s+(?!(?:Nature|Science|General|Practice|Theory|Process|System|Market|Public|Private|Common|Control|Research|Development|Management|Support|Security|Service|Report|History|Current|Future|Recent|Final|Total|Average|Standard|Normal|Special|Maintenance|Text|Mode|Progress|Review|Summary|Detail|Analysis|Backticks|Quotes|Brackets|Parentheses|Here|There|This|That|These|Those|The|A|An)\b)[A-Z][a-z]{3,}\b(?=\s*,|\s*\.|\s*-|\s+and|\s+or|\s*$)", 0.50),
    # City in population context: "X (37M), Y (32M)"
        ("CITY", r"(?i)\b[A-Z][a-z]+\s*\(\d+\s*M\)", 0.55),
        # Standalone city name at sentence start or after period+space
        ("CITY", r"(?<!\d\s)(?:^|\.\s+)(?:Paris|London|Berlin|Mumbai|Tokyo|Delhi|Shanghai|Sydney|Moscow|Rome|Madrid|Cairo|Dubai|Istanbul|Seoul|Bangkok|New York|Chicago|Los Angeles|Toronto|Vancouver|Boston|San Francisco|Amsterdam|Vienna|Zurich|Redmond|Seattle|Austin|Denver)\b", 0.40),
        # City before comma+non-country (like postcode, street suffix) — lower confidence
        ("CITY", r"\b(?:Paris|London|Berlin|Mumbai|Tokyo|Delhi|Shanghai|Sydney|Moscow|Rome|Madrid|Cairo|Dubai|Istanbul|Seoul|Bangkok|New York|Chicago|Los Angeles|Toronto|Vancouver|Boston|San Francisco|Amsterdam|Vienna|Zurich|Redmond|Seattle|Austin|Denver)(?=\s*,\s*[A-Z0-9])", 0.35),
        # City after "of" keyword — use lookbehind so "of " isn't part of the match.
        # Split into two fixed-width lookbehinds: one for "of " and one for "city of "
        # Exclude common country names to avoid COUNTRY→CITY confusion
        ("CITY", r"(?i)(?<=of )(?!(?:Germany|France|Italy|Spain|UK|USA|US|Canada|Australia|England|China|India|Japan|Brazil|Mexico|Russia|Poland|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Turkey|Greece|Egypt|Thailand|Vietnam|Latin)\b)(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.40),
        ("CITY", r"(?i)(?<=city of )(?!(?:Germany|France|Italy|Spain|UK|USA|US|Canada|Australia|England|China|India|Japan|Brazil|Mexico|Russia|Poland|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Turkey|Greece|Egypt|Thailand|Vietnam)\b)(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.40),

    # ── COUNTRY ──────────────────────────────────────────────────────
    ("COUNTRY", r"\b(?:USA|US(?:A)?|UK|United States|United Kingdom|Canada|Australia|Germany|France|Italy|Spain|Japan|China|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|South Korea|Argentina|Chile|Colombia|Egypt|Nigeria|South Africa|Kenya|Thailand|Vietnam|Philippines|Indonesia|Malaysia|Singapore|New Zealand|Saudi Arabia|UAE|Israel|Greece|Czech|Finland|Hungary|Romania|Ukraine)\b", 0.80),

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
    ("COMPANY", r"(?i)(?:(?:work|works)\s+at|Invoice\s+from|Signed\s+by|regarding)\s+(?:(?:the|our)\s+)?(?-i:[A-Z])[a-z]{3,}(?:(?:\s+(?:(?:the|our|and)\s+)?(?-i:[A-Z])[a-z]{2,}))?\b", 0.65),
    # "Company: X" / "Vendor: X" / "Organization: X" prefix — NOT "Client:" which
    # often precedes a person name.
    ("COMPANY", r"(?i)(?:Company|Vendor|Organization)\s*[：:]\s*(?:(?:the|our)\s+)?(?-i:[A-Z])[a-z]{2,}(?:\s+(?:(?:the|our|and)\s+)?(?-i:[A-Z])[a-z]+)?\b", 0.70),
    # "X is the vendor" / "X is our vendor" / "X is a vendor"
    ("COMPANY", r"(?-i:[A-Z])[a-z]{3,}(?:\s+(?:(?:the|our|and)\s+)?(?-i:[A-Z])[a-z]+)?\s+is\s+(?:the|our|a)\s+vendor\b", 0.65),
    # Two capitalized words acting as company name (no suffix needed) in
    # company context — preceded by known company keywords.
    ("COMPANY", r"(?i)(?:(?:work|works)\s+at|Invoice\s+from|Signed\s+by|regarding)\s+(?-i:[A-Z])[a-z]+(?:\s+(?:(?:the|our|and|n|'n)\s+)?(?-i:[A-Z])[a-z]+)\b", 0.60),
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
    ("COMPANY", r"(?<!\w)(?<!\()(?:from)\s+(?-i:[A-Z])[a-z]+(?:\s+(?:(?:the|our|and|n|'n)\s+)?(?-i:[A-Z])[a-z]+)(?![^(]*\))(?!\s*(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co\.?|Company|Corporation|PLC|AG|SA|BV|NV))\b", 0.50),

]