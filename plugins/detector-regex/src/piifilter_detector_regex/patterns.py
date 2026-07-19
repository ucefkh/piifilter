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
    # Context-prefixed phone numbers — only match when preceded by phone-related keywords
    ("PHONE", r"(?i)\b(?:phone|tel|telephone|mobile|cell|call)\s*(?:number|no|#)?\s*:?\s*[\+\d\(][\d\s\-\.\(\)]{7,20}\b", 0.90),
    # International phone numbers with explicit country code (+ or opening paren)
    ("PHONE", r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b", 0.85),
    # Phones with parentheses area code: (415) 555-2671
    ("PHONE", r"\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b", 0.85),
    # Simple 10-digit: 555-123-4567 (typically US/Canada)
    ("PHONE", r"\b\d{3}[-]\d{3}[-]\d{4}\b", 0.80),

    # ── CREDIT_CARD ──────────────────────────────────────────────────
    # Context-prefixed credit card — only match when preceded by relevant keywords
    ("CREDIT_CARD", r"(?i)\b(?:credit\s*card|cc|card)\s*(?:number|no|#)?\s*:?\s*\d[ -]*?\d{13,18}\b", 0.90),
    # 14-19 digit card numbers with common separators (spaces, dashes)
    # Fallback when no context keyword is present — lower confidence
    ("CREDIT_CARD", r"\b(?:\d[ -]*?){14,19}\b", 0.70),

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
    ("GPS", r"\b(?:lat|latitude)\s*[:=]?\s*[-+]?\d+(?:\.\d+)?\s*[,;]\s*(?:lon|lng|longitude)\s*[:=]?\s*[-+]?\d+(?:\.\d+)?\b", 0.90),

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
    # Context-prefixed bank account — only match when preceded by relevant keywords
    ("BANK_ACCOUNT", r"(?i)\b(?:bank|account|acct)\s*(?:number|no|#)?\s*:?\s*\d{8,17}\b", 0.85),
    # Bare 8-17 digit sequence — fallback when no context keyword present
    ("BANK_ACCOUNT", r"\b\d{8,17}\b", 0.65),

    # ── PASSPORT ─────────────────────────────────────────────────────
    # Context-prefixed passport — only match when preceded by relevant keywords
    ("PASSPORT", r"(?i)\b(?:passport)\s*(?:number|no|#)?\s*:?\s*[A-Z]{0,2}\d{6,9}\b", 0.85),
    # Passport number patterns (letters + digits, 6-9 chars)
    ("PASSPORT", r"\b[A-Z]{1,2}\d{6,9}\b", 0.75),
    ("PASSPORT", r"\b\d{8,9}\b", 0.65),

    # ── SSH_KEY ──────────────────────────────────────────────────────
    # SSH private key markers
    ("SSH_KEY", r"-----BEGIN(?: OPENSSH| RSA| DSA| EC| ECDSA)? PRIVATE KEY-----", 0.95),

    # ── PERSON ───────────────────────────────────────────────────────
    # Named entity patterns: title-prefixed names (Mr. Smith, Dr. Jones, etc.)
    ("PERSON", r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", 0.85),
    # First-name Last-name preceded by context (my name is, i'm, introduce, contact person, etc.)
    ("PERSON", r"(?i)\b(?:my name is|i'm|i am|call me|name is|introduce)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b", 0.80),
    # "ROLE + Name" patterns: Our CEO/President/Director + Capitalized Name
    ("PERSON", r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", 0.75),

    # ── ADDRESS ──────────────────────────────────────────────────────
    # Street addresses: number + street name + street type
    ("ADDRESS", r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b", 0.80),
    # PO Box
    ("ADDRESS", r"\bP\.?\s*O\.?\s+Box\s+\d+\b", 0.85),
    # Suite/Apt number
    ("ADDRESS", r"\b(?:Suite|Apt|Unit|Building)\s+#?\d+[A-Za-z]?\b", 0.80),

    # ── CITY ─────────────────────────────────────────────────────────
    # Not reliable via regex — handled by Presidio or GLiNER. Minimal heuristic:
    # Common US/EU city names that start with capital letter (low confidence)
    ("CITY", r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*(?:,|\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?)\b", 0.70),

    # ── COUNTRY ──────────────────────────────────────────────────────
    # Common country names (exhaustive-ish list)
    ("COUNTRY", r"\b(?:USA|US(?:A)?|UK|United States|United Kingdom|Canada|Australia|Germany|France|Italy|Spain|Japan|China|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|South Korea|Argentina|Chile|Colombia|Egypt|Nigeria|South Africa|Kenya|Thailand|Vietnam|Philippines|Indonesia|Malaysia|Singapore|New Zealand|Saudi Arabia|UAE|Israel|Greece|Czech|Finland|Hungary|Romania|Ukraine)\b", 0.80),

    # ── COMPANY ──────────────────────────────────────────────────────
    # Company suffixes
    ("COMPANY", r"\b[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*(?:\s+(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|Incorporated|PLC|AG|SA|BV|NV))\.?\b", 0.80),
    # Tech companies common patterns
    ("COMPANY", r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\s+(?:Technologies|Tech|Systems|Software|Solutions|Group|Partners|Holdings|Enterprises|Ventures|Industries|Global|International|Digital|Media|Networks|Services|Consulting|Associates)\b", 0.75),

    # ── CUSTOMER_NAME / EMPLOYEE_NAME / PROJECT_NAME ─────────────────
    # These are domain-specific — regex can only approximate with context prefixes
    ("CUSTOMER_NAME", r"(?i)\b(?:customer|client|account)\s+(?:name\s+)?(?:is\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", 0.75),
    ("EMPLOYEE_NAME", r"(?i)\b(?:employee|staff|teammate|colleague|manager|supervisor|engineer|developer|designer)\s+(?:name\s+)?(?:is\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", 0.75),
    ("PROJECT_NAME", r"(?i)\b(?:project|initiative|campaign|program)\s+(?:name\s+)?(?:is\s+)?(?:called\s+)??[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*\b", 0.75),
    # Project codenames like "Project X", "Operation Y"
    ("PROJECT_NAME", r"\b(?:Project|Operation|Initiative|Program|Code[- ]?name)\s+[A-Z][a-zA-Z0-9]+\b", 0.80),
]