"""Regex pattern definitions for PII detection.

All patterns are separated from detection logic so they can be
inspected, tested, or extended independently.
"""

from __future__ import annotations

# Each tuple: (entity_type_name, regex_pattern, confidence_score)
# Patterns are ordered — more specific patterns come before general ones
# to avoid false positives from broader patterns.

PATTERN_DEFS: list[tuple[str, str, float]] = [
    # ── EMAIL ────────────────────────────────────────────────────────
    # Standard RFC-like email addresses
    ("EMAIL", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 0.90),

    # ── JWT ──────────────────────────────────────────────────────────
    # base64.base64.base64 — must come before DOMAIN to avoid
    # JWT tokens being misclassified as domain names
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b", 0.95),

    # ── DOMAIN ───────────────────────────────────────────────────────
    # Domain names (not just email extracts)
    ("DOMAIN", r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", 0.85),

    # ── API_KEY ──────────────────────────────────────────────────────
    # Common key prefixes (sk-, pk-, etc.) — capture full key value
    ("API_KEY", r"\b(?:sk-|pk-|api[-_]?key|token|secret)[-_]?[a-zA-Z0-9_\-]{16,64}\b", 0.95),
    ("API_KEY", r"\b(?:[A-Za-z0-9+/=]{20,})\b(?=.*(?:key|token|secret))", 0.90),

    # ── SSN (US Social Security) ─────────────────────────────────────
    # ###-##-#### — must come before PHONE to avoid misclassification
    ("SSN", r"\b\d{3}[-]\d{2}[-]\d{4}\b", 0.90),

    # ── PHONE ────────────────────────────────────────────────────────
    # International phone numbers (must start with digit or +)
    ("PHONE", r"\b(?:\+?\d{1,3}[-.\s]?)?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", 0.85),

    # ── CREDIT_CARD ──────────────────────────────────────────────────
    # 13-19 digit card numbers (Luhn-likely)
    ("CREDIT_CARD", r"\b(?:\d[ -]*?){13,19}\b", 0.85),

    # ── IP_ADDRESS ───────────────────────────────────────────────────
    # IPv4
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", 0.90),
    # IPv6 (simplified)
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.85),
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}\b", 0.80),

    # ── DATABASE_URL ─────────────────────────────────────────────────
    # Connection strings
    ("DATABASE_URL", r"\b(?:postgresql|postgres|mysql|mongodb|redis|sqlite|oracle|mssql)://\S+", 0.95),

    # ── GPS ──────────────────────────────────────────────────────────
    # Lat/lng coordinates (must have explicit comma or separator)
    ("GPS", r"[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?)\s*[°º]?\s*[,;]\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|\d{1,2})(?:\.\d+)?)\s*[°º]?", 0.85),
    ("GPS", r"\b(?:lat|latitude)\s*[:=]\s*[-+]?\d+(?:\.\d+)?\s*[,;]\s*(?:lon|lng|longitude)\s*[:=]\s*[-+]?\d+(?:\.\d+)?\b", 0.90),

    # ── FILE_PATH ────────────────────────────────────────────────────
    # Unix absolute paths (minimum 3 levels deep with / separators)
    ("FILE_PATH", r"(?<!/)/(?:[a-zA-Z0-9._-]+/){3,}[a-zA-Z0-9._-]*(?!\w)", 0.85),
    # Common Unix root patterns explicitly (2 levels minimum)
    ("FILE_PATH", r"(?<!/)/(?:home|var|etc|usr|opt|tmp|root|mnt|media|run|srv)/(?:[a-zA-Z0-9._-]+/?)+[a-zA-Z0-9._-]+(?!\w)", 0.90),
    # Windows absolute paths
    ("FILE_PATH", r"(?<!\w)(?:[A-Za-z]:\\[a-zA-Z0-9._\\ -]+)(?!\w)", 0.90),

    # ── PRIVATE_URL ──────────────────────────────────────────────────
    # Internal/hosted URLs (localhost, private IPs, private domains)
    ("PRIVATE_URL", r"\b(?:https?://)?(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\b(?:https?://)?[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.\w+)*(?::\d+)?(?:/[^\s]*)?\b", 0.90),

    # ── IBAN ─────────────────────────────────────────────────────────
    # International bank account numbers
    ("IBAN", r"\b[A-Z]{2}\d{2}[ ]?(?:\d{4}[ ]?){4,7}\d?\b", 0.85),

    # ── BANK_ACCOUNT ─────────────────────────────────────────────────
    # Common bank account formats (8-17 digits)
    ("BANK_ACCOUNT", r"\b\d{8,17}\b", 0.75),

    # ── PASSPORT ─────────────────────────────────────────────────────
    # Passport number patterns (letters + digits, 6-9 chars)
    ("PASSPORT", r"\b[A-Z]{1,2}\d{6,9}\b", 0.75),
    ("PASSPORT", r"\b\d{8,9}\b", 0.70),

    # ── SSH_KEY ──────────────────────────────────────────────────────
    # SSH private key markers
    ("SSH_KEY", r"-----BEGIN(?: OPENSSH| RSA| DSA| EC| ECDSA)? PRIVATE KEY-----", 0.95),
]