"""High-speed regex-based PII detector."""
from __future__ import annotations

import re
from typing import Pattern

from piifilter.shared.models import DetectedEntity, EntityType


class RegexDetector:
    """Detects PII entities using compiled regex patterns.

    Scores all matches between 0.85–0.95 based on pattern specificity.
    """

    def __init__(self) -> None:
        self.patterns: list[tuple[EntityType, Pattern[str], float]] = self._compile_patterns()

    # ------------------------------------------------------------------
    # Pattern definitions
    # ------------------------------------------------------------------
    _PATTERN_DEFS: list[tuple[str, str, float]] = [
        # EMAIL — standard RFC-like email addresses
        ("EMAIL", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 0.90),

        # JWT — base64.base64.base64 pattern
        # Must come before DOMAIN to avoid JWT tokens being misclassified as domain names
        ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b", 0.95),

        # DOMAIN — domain names (not just email extracts)
        ("DOMAIN", r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", 0.85),

        # API_KEY — common key prefixes (sk-, pk-, etc.) — capture full key value
        ("API_KEY", r"\b(?:sk-|pk-|api[-_]?key|token|secret)[-_]?[a-zA-Z0-9_\-]{16,64}\b", 0.95),
        ("API_KEY", r"\b(?:[A-Za-z0-9+/=]{20,})\b(?=.*(?:key|token|secret))", 0.90),

        # SOCIAL_SECURITY — US SSN (###-##-####)
        # Must come before PHONE to avoid misclassification
        ("SOCIAL_SECURITY", r"\b\d{3}[-]\d{2}[-]\d{4}\b", 0.90),

        # PHONE — international phone numbers (must start with digit or +)
        ("PHONE", r"\b(?:\+?\d{1,3}[-.\s]?)?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", 0.85),

        # CREDIT_CARD — 13-19 digit card numbers (Luhn-likely)
        ("CREDIT_CARD", r"\b(?:\d[ -]*?){13,19}\b", 0.85),

        # IP_ADDRESS — IPv4
        ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", 0.90),

        # IP_ADDRESS — IPv6 (simplified)
        ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.85),
        ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}\b", 0.80),

        # DATABASE_URL — connection strings
        ("DATABASE_URL", r"\b(?:postgresql|postgres|mysql|mongodb|redis|sqlite|oracle|mssql)://\S+", 0.95),

        # GPS — lat/lng coordinates (must have explicit comma or separator between values)
        ("GPS", r"[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?)\s*[°º]?\s*[,;]\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|\d{1,2})(?:\.\d+)?)\s*[°º]?", 0.85),
        ("GPS", r"\b(?:lat|latitude)\s*[:=]\s*[-+]?\d+(?:\.\d+)?\s*[,;]\s*(?:lon|lng|longitude)\s*[:=]\s*[-+]?\d+(?:\.\d+)?\b", 0.90),

        # COMPANY — proper nouns ending in Corp, Inc, LLC, etc.
        ("COMPANY", r"\b[A-Z][a-zA-Z]+(?:Corp|Corporation|Inc|Incorporated|LLC|Ltd|Limited|GmbH|SA|SARL|SAS)\b", 0.85),
        ("COMPANY", r"\b[A-Z][a-zA-Z]+(?:Corp|Inc|LLC|Ltd|GmbH)\b", 0.80),

        # FILE_PATH — Unix absolute paths (minimum 3 levels deep with / separators)
        ("FILE_PATH", r"(?<!\w)/(?:[a-zA-Z0-9._-]+/){3,}[a-zA-Z0-9._-]*(?!\w)", 0.85),
        # FILE_PATH — also match common Unix root patterns explicitly (2 levels minimum)
        ("FILE_PATH", r"(?<!\w)/(?:home|var|etc|usr|opt|tmp|root|mnt|media|run|srv)/(?:[a-zA-Z0-9._-]+/?)+[a-zA-Z0-9._-]+(?!\w)", 0.90),
        # FILE_PATH — Windows absolute paths
        ("FILE_PATH", r"(?<!\w)(?:[A-Za-z]:\\[a-zA-Z0-9._\\ -]+)(?!\w)", 0.90),

        # PRIVATE_URL — internal/hosted URLs
        ("PRIVATE_URL", r"\b(?:https?://)?(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(?::\d+)?(?:/[^\s]*)?\b", 0.90),
        ("PRIVATE_URL", r"\b(?:https?://)?[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.\w+)*(?::\d+)?(?:/[^\s]*)?\b", 0.90),

        # IBAN — international bank account numbers
        ("IBAN", r"\b[A-Z]{2}\d{2}[ ]?(?:\d{4}[ ]?){4,7}\d?\b", 0.85),

        # BANK_ACCOUNT — common bank account formats (8-17 digits)
        ("BANK_ACCOUNT", r"\b\d{8,17}\b", 0.75),

        # PASSPORT — passport number patterns (letters + digits, 6-9 chars)
        ("PASSPORT", r"\b[A-Z]{1,2}\d{6,9}\b", 0.75),
        ("PASSPORT", r"\b\d{8,9}\b", 0.70),

        # SSH_KEY — SSH private key markers
        ("SSH_KEY", r"-----BEGIN(?: OPENSSH| RSA| DSA| EC| ECDSA)? PRIVATE KEY-----", 0.95),
    ]

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------
    def _compile_patterns(self) -> list[tuple[EntityType, Pattern[str], float]]:
        """Compile static pattern definitions into (EntityType, Pattern, score) tuples."""
        compiled: list[tuple[EntityType, Pattern[str], float]] = []
        for type_name, raw_pattern, score in self._PATTERN_DEFS:
            entity_type = EntityType(type_name)
            pattern = re.compile(raw_pattern, re.IGNORECASE)
            compiled.append((entity_type, pattern, score))
        return compiled

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def detect(self, text: str) -> list[DetectedEntity]:
        """Run all regex patterns against *text* and return non-overlapping results."""
        if not text:
            return []

        entities: list[DetectedEntity] = []
        seen_intervals: list[tuple[int, int]] = []  # for basic overlap dedup

        for entity_type, pattern, score in self.patterns:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                matched_text = match.group()

                # Skip zero-length matches
                if start == end:
                    continue

                # Skip if fully contained in an already-found match of the same type
                if any(s <= start and end <= e for s, e in seen_intervals):
                    continue

                entities.append(
                    DetectedEntity(
                        text=matched_text,
                        type=entity_type,
                        start=start,
                        end=end,
                        score=score,
                        source_detector="regex",
                    )
                )
                seen_intervals.append((start, end))

        # Sort by start position
        entities.sort(key=lambda e: e.start)
        return entities