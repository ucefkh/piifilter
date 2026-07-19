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

    # ── JWT ──────────────────────────────────────────────────────────
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b", 0.95),
    # Truncated JWT (two parts, common in abbreviated context)
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.\.\.\w*\b", 0.90),
    ("JWT", r"\beyJ[a-zA-Z0-9_-]{3,20}\.\.\.[a-zA-Z0-9_-]{3,10}\b", 0.85),
    # JWT with 3 dots as ellipsis: "eyJzdW...IyfQ"
    ("JWT", r"\beyJ[a-zA-Z0-9_-]+\.\.\.[a-zA-Z0-9_-]+\b", 0.85),
    # JWT that is essentially a base64 encoded payload (single segment, no dots)
    ("JWT", r"\beyJ[a-zA-Z0-9+/=_-]{20,}\b", 0.70),

    # ── DATABASE_URL ─────────────────────────────────────────────────
    ("DATABASE_URL", r"\b(?:postgresql|postgres|mysql|mongodb|redis|sqlite|oracle|mssql)://\S+", 0.95),

    # ── SSN ──────────────────────────────────────────────────────────
    ("SOCIAL_SECURITY", r"\b\d{3}[-]\d{2}[-]\d{4}\b", 0.90),

    # ── CREDIT_CARD ──────────────────────────────────────────────────
    ("CREDIT_CARD", r"(?i)\b(?:credit\s*card|cc|card)\s*(?:number|no|#)?\s*:?\s*\d[ -]*?\d{13,18}\b", 0.90),
    # Standard 4-4-4-4 format with dashes — must NOT be inside an IBAN (not preceded by [A-Z]{2}\d{2}\s)
    # and must NOT be followed by more space-separated digit groups (which is an IBAN feature)
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b(?![ -]\d{2,4})", 0.85),
    ("CREDIT_CARD", r"\b\d{4}[- ]\d{6}[- ]\d{5}\b", 0.80),
    # Low confidence: 4-4-4-2..4 pattern — must NOT have an IBAN-like preceding block or additional digit groups.
    # Must NOT be the trailing portion of an IBAN (preceded by a digit-group and space).
    ("CREDIT_CARD", r"(?<![A-Z]{2}\d{2}\s)(?<![A-Za-z])(?<!\d{4}[- ])\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{2,4}\b(?![- ]\d{2,4})(?!\s*\d{2,4})", 0.65),
    # Continuous 16-digit credit card numbers (no dashes) — Luhn-prefixed only
    ("CREDIT_CARD", r"(?i)(?:credit\s*card|cc|card\s+#?)\b\s*\d{16}\b", 0.80),
    ("CREDIT_CARD", r"\b(?:4\d{3}|5[1-5]\d{2}|6\d{3}|3[47]\d{2})\d{12}\b", 0.80),
    # Generic 16-digit number — low confidence
    ("CREDIT_CARD", r"\b\d{16}\b", 0.55),

    # ── EMAIL ────────────────────────────────────────────────────────
    ("EMAIL", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 0.90),

    # ── API_KEY ──────────────────────────────────────────────────────
    ("API_KEY", r"\b(?:sk-|pk-|api[-_]?key|token|secret)[-_]?[a-zA-Z0-9_\-]{16,64}\b", 0.95),
    ("API_KEY", r"\b(?:[A-Za-z0-9+/=]{20,})\b(?=.*(?:key|token|secret))", 0.90),

    # ── IBAN ─────────────────────────────────────────────────────────
    ("IBAN", r"\b[A-Z]{2}\d{2}(?:[ ]?(?:[A-Z0-9]{4})){4,7}(?:[ ]?\d{1,4})?\b", 0.85),

    # ── PHONE ────────────────────────────────────────────────────────
    ("PHONE", r"(?i)\b(?:phone|tel|telephone|mobile|cell|call)\s*(?:number|no|#)?\s*[\-]?\s*[\+\d\(][\d\s\-\.\(\)]{7,20}\b", 0.90),
    ("PHONE", r"(?:^|\s)\+\d{1,3}[-.\s]\d{2,4}[-.\s]\d{3,4}[-.\s]\d{4}\b", 0.88),
    ("PHONE", r"(?:^|\s)\+\d{1,3}\s+\d{2,3}\s+\d{3}\s+\d{3,4}\b", 0.85),
    ("PHONE", r"(?:^|\s)\+\d\s+\d{3}\s+\d{3}[-.\s]?\d{2}[-.\s]?\d{2}\b", 0.85),
    ("PHONE", r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]?\d{4}\b", 0.85),
    ("PHONE", r"\b\d{3}-\d{3}-\d{4}\b", 0.70),
    # UK mobile format: 07XXX XXX XXX (after "Phone:" keyword)
    ("PHONE", r"(?i)\bPhone:\s*\d{5}\s+\d{3}\s+\d{3}\b", 0.80),
    # Phone numbers after CJK 电话/電話 keywords
    ("PHONE", r"(?i)(?:电话|電話)\+[\d-]+[\s-]?\d{3,4}[\s-]?\d{4,}\b", 0.85),
    # CJK phone: 電話は+X XX-XXXX-XXXX (Japanese context)
    ("PHONE", r"(?i)(?:電話は|电话是|電話)\s*\+\d+[\s-]?\d+[\s-]?\d+[\s-]?\d+\b", 0.85),
    # German format after Phone: — "+49 30 12345678"
    ("PHONE", r"(?i)\bPhone:\s*\+\d{1,3}\s+\d{2,4}\s+\d{5,10}\b", 0.80),

    # ── PRIVATE_URL ──────────────────────────────────────────────────
    ("PRIVATE_URL", r"\bhttps?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\bhttps?://[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.[\w-]+)*(?::\d+)?(?:/[^\s]*)?\b", 0.90),
    ("PRIVATE_URL", r"\b[\w-]+\.(?:internal|local|private|corp|intranet)(?:\.[\w-]+)*(?::\d+)(?:/[^\s]*)?\b", 0.85),

    # ── IP_ADDRESS ───────────────────────────────────────────────────
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", 0.90),
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.88),
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){1,5}::(?:[0-9a-fA-F]{1,4}:){0,4}[0-9a-fA-F]{1,4}\b", 0.85),
    ("IP_ADDRESS", r"\b::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b", 0.85),
    ("IP_ADDRESS", r"\b(?:[0-9a-fA-F]{1,4}:){1,7}::\b", 0.85),

    # ── GPS ──────────────────────────────────────────────────────────
    ("GPS", r"\b(?:lat|lng|lon|latitude|longitude|coordinates?|coords?|gps)\s*[:=]?\s*[-+]?\d{1,3}\.\d+(?:\s*°)?", 0.90),
    ("GPS", r"[-+]?\d{1,2}\.\d{4,}\s*[,;]\s*[-+]?\d{1,3}\.\d{4,}", 0.88),
    ("GPS", r"[-+]?\d{1,2}\.\d+\s*°?\s*[NS]\s*[,;]?\s*[-+]?\d{1,3}\.\d+\s*°?\s*[EW]", 0.85),
    # Individual decimal coordinates — match after keyword: "Coordinates: 40.7128"
    ("GPS", r"(?i)(?:lat|lng|lon|latitude|longitude|coordinates|coord|gps)\s*[:=]\s*[-+]?\d{1,3}\.\d{4,}", 0.88),
    # Individual numbers that are clearly coordinates (2-digit integer part, 4+ decimal places)
    ("GPS", r"(?<!\d)(?<!\d\.)[-+]?\d{1,2}\.\d{4,}(?!\d)", 0.70),

    # ── FILE_PATH ────────────────────────────────────────────────────
    ("FILE_PATH", r"(?<!\/)/(?:[a-zA-Z0-9._-]+/){3,}[a-zA-Z0-9._-]*(?!\w)", 0.85),
    ("FILE_PATH", r"(?<!\/)/(?:home|var|etc|usr|opt|tmp|root|mnt|media|run|srv)/(?:[a-zA-Z0-9._-]+/?)+[a-zA-Z0-9._-]+(?!\w)", 0.90),
    ("FILE_PATH", r"(?<!\w)(?:[A-Za-z]:\\[a-zA-Z0-9._\\ -]+)(?!\w)", 0.90),

    # ── DOMAIN ───────────────────────────────────────────────────────
    ("DOMAIN", r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", 0.75),

    # ── PASSPORT ─────────────────────────────────────────────────────
    ("PASSPORT", r"(?i)(?:^|\s)(?:passport)\s*(?:number|no|#)?\s*:?\s*[A-Z]{0,2}\d{6,9}\b", 0.85),
    ("PASSPORT", r"\b[A-Z]{1,2}\d{6,9}\b", 0.75),

    # ── BANK_ACCOUNT ─────────────────────────────────────────────────
    ("BANK_ACCOUNT", r"(?i)\b(?:bank|account|acct)\s*(?:number|no|#)?\s*:?\s*\d{8,17}\b", 0.85),
    # Non-IBAN-looking digit sequences — exclude those starting with 2 letters
    ("BANK_ACCOUNT", r"(?<![A-Za-z])\b\d{12,20}\b", 0.55),

    # ── PERSON ───────────────────────────────────────────────────────
    # Title-prefixed — name must be 2+ chars, not a single letter
    ("PERSON", r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.85),
    # "I'm/My name is/Call me + Name"
    ("PERSON", r"(?i)(?:\bmy name is|\bI'm|\bcall me|\bname is)\s+(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,}){0,2}\b", 0.80),
    # "ROLE + Name" — exclude common role/researcher-type words after the name
    ("PERSON", r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.75),
    # "Person:" prefix — handle titles like Dr., Mr. — require at least one real name word
    ("PERSON", r"(?i)\bPerson:\s*(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Hon)\.?\s+)?(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.80),
    # "Contact person:" / "Contact name:"
    ("PERSON", r"(?i)\bContact\s+(?:person|name):\s*(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.80),
    # Unicode/Non-Latin names — matched by context keywords (CJK + common non-Latin alphabet names)
    # CJK: keyword 用户/联系人/姓名 directly followed by name (no colon needed)
    # Exclude common technical terms that look like capitalized names (Postgresql, Admin, Root, etc.)
    ("PERSON", r"(?i)\b(?:contact|person)\s*[：:]\s*[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b", 0.75),
    # user: prefix — more restrictive to avoid technical terms like 'user: postgresql'
    ("PERSON", r"(?i)\buser\s*[：:](?!\s*(?:admin|root|postgres|postgresql|mysql|default|guest|test|anonymous|nobody|system|api|service))\s*[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b", 0.70),
    # CJK-specific: 用户/联系人/姓名 directly followed by 2+ CJK characters
    ("PERSON", r"(?:用户|联系人|姓名|名前)[：:]?\s*[\u4e00-\u9fff]{2,4}(?:\s+[\u4e00-\u9fff]{2,4})?\b", 0.80),
    # Russian/Cyrillic names
    ("PERSON", r"(?i)\b(?:contact|user|person|connect|reach)\s+(?:is|name)\s+[\u0400-\u04ff]+\b", 0.75),
    # Arabic script names — handle بـ prefix (U+0628 + optional tatweel U+0640)
    ("PERSON", r"(?i)\b(?:اتصل)\s+بـ?\s*[\u0600-\u06ff]+\b", 0.80),
    ("PERSON", r"(?i)\b(?:اسم|اسمي)\s+[\u0600-\u06ff]+\b", 0.80),
    # Japanese: CJK name followed by の (possessive) or さん (honorific)
    ("PERSON", r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,4}(?:の|さん)\b", 0.70),
    # Greek alphabet names (O + name pattern for "O Γιώργος")
    ("PERSON", r"(?i)\bO\s+[\u0370-\u03ff]+\b", 0.70),
    # Any non-Latin name caught by context + multiple non-Latin word chars
    ("PERSON", r"\b(?:name|email|phone|mail|contact|user)\s*[：:]\s*[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff]+\b", 0.65),
    # Non-Latin names after language labels — use lookbehind so match starts at the name
    ("PERSON", r"(?i)(?:(?<=Russian:)|(?<=Arabic:)|(?<=Japanese:)|(?<=Greek:)|(?<=Unicode))\s*(?-i:[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])[a-z0-9\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]*(?:\s+(?-i:[\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])[a-z0-9\u0400-\u04ff\u0600-\u06ff\u0370-\u03ff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]*)?\b", 0.70),

    # ── CUSTOMER_NAME ────────────────────────────────────────────────
    ("CUSTOMER_NAME", r"(?i)\b(?:customer|client)\s+(?:name\s+)?(?:is\s+)?(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("CUSTOMER_NAME", r"(?i)\bCustomer:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("CUSTOMER_NAME", r"(?i)\bcustomer\s+(?:we\s+)?(?:have|here)\s+is\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.75),

    # ── EMPLOYEE_NAME ────────────────────────────────────────────────
    ("EMPLOYEE_NAME", r"(?i)\b(?:employee|staff|teammate|colleague|manager|supervisor|engineer|developer|designer)\s+(?:name\s+)?(?:is\s+)?(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("EMPLOYEE_NAME", r"(?i)\b(?:employee|staff)\s+(?:named|name)\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("EMPLOYEE_NAME", r"(?i)\bEmployee:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.80),
    ("EMPLOYEE_NAME", r"(?i)\b(?:add\s+)?employee\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b", 0.75),

    # ── PROJECT_NAME ─────────────────────────────────────────────────
    ("PROJECT_NAME", r"(?i)\b(?:project|initiative|campaign|program)\s+(?:name\s+)?(?:is\s+)?(?:called\s+)?(?-i:[A-Z])[a-zA-Z0-9]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)*\b", 0.80),
    ("PROJECT_NAME", r"\b(?:Project|Operation|Initiative|Program|Code[- ]?name)\s+(?-i:[A-Z])[a-zA-Z0-9]+\b", 0.85),

    # ── ADDRESS ──────────────────────────────────────────────────────
        # Standard address: "N Street Name St/Rd/Ave/etc."
        # Uses negative lookbehind (?<!not\s) to block ", not 123 Main St" teaching patterns.
        # Uses a general negative lookahead for parentheticals that look like media references
        # ("(famous from Finding Nemo)", "(from the movie...)") rather than address clarifications.
        ("ADDRESS", r"\b(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:movie|show|film|game|series|cartoon|animation|episode|from\s+[A-Z]))\b", 0.80),
    ("ADDRESS", r"\bP\.?\s*O\.?\s+Box\s+\d+\b", 0.85),
    ("ADDRESS", r"\b(?:Suite|Apt|Unit|Building)\s+#?\d+[A-Za-z]?\b", 0.80),

    # ── CITY ─────────────────────────────────────────────────────────
    ("CITY", r"(?i)\b(?:city|town)\s*(?:of|pop|population)?\s*:?\s*(?!(?:The|A|An|This|That|These|Those|Our|Their|My|Your|His|Her|Its)\b)[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?\b", 0.70),
    # Cities followed by comma + known country — exclude country names from city position
    ("CITY", r"\b(?!(?:Canada|Australia|Germany|France|Italy|Spain|Japan|China|India|Brazil|Mexico|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Poland|Russia|Turkey|South Korea|Argentina|Chile|Colombia|Egypt|Nigeria|South Africa|Kenya|Thailand|Vietnam|Philippines|Indonesia|Malaysia|Singapore|New Zealand|Saudi Arabia|UAE|Israel)\s*,)[A-Z][a-z]+\s*,\s+(?:Germany|France|Italy|Spain|UK|England|USA|US|China|Japan|India|Brazil|Canada|Australia)\b", 0.70),
    # City after "works at X in City" or "based in City"
        ("CITY", r"(?i)\b(?:based\s+in|works?\s+(?:at\s+\S+\s+)?in|lives?\s+in|located\s+in|situated\s+in)\s+(?-i:[A-Z])[a-z]{2,}\b", 0.60),
        # City after "in" followed by comma and country or end of context
        # Require 4+ chars and exclude common non-city capitalized words
        ("CITY", r"(?i)\bin\s+(?!(?:Nature|Science|General|Practice|Theory|Process|System|Market|Public|Private|Common|Control|Research|Development|Management|Support|Security|Service|Report|History|Current|Future|Recent|Final|Total|Average|Standard|Normal|Special|Maintenance|Text|Mode|Progress|Review|Summary|Detail|Analysis)\b)[A-Z][a-z]{3,}(?:\s*,\s*(?:Germany|France|Italy|Spain|UK|USA|Canada|Australia))?\b", 0.50),
    # City in population context: "X (37M), Y (32M)"
        ("CITY", r"(?i)\b[A-Z][a-z]+\s*\(\d+\s*M\)", 0.55),
        # Standalone city name — match at sentence start or before comma+known country
        # Also requires the city NOT be preceded by a street address number pattern
        ("CITY", r"(?<!\d\s)(?:(?:^|\.\s+)(?:Paris|London|Berlin|Mumbai|Tokyo|Delhi|Shanghai|Sydney|Moscow|Rome|Madrid|Cairo|Dubai|Istanbul|Seoul|Bangkok|New York|Chicago|Los Angeles|Toronto|Vancouver|Boston|San Francisco|Amsterdam|Vienna|Zurich|Redmond|Seattle|Austin|Denver)\b|(?:Paris|London|Berlin|Mumbai|Tokyo|Delhi|Shanghai|Sydney|Moscow|Rome|Madrid|Cairo|Dubai|Istanbul|Seoul|Bangkok|New York|Chicago|Los Angeles|Toronto|Vancouver|Boston|San Francisco|Amsterdam|Vienna|Zurich|Redmond|Seattle|Austin|Denver)\s*,\s*(?:Germany|France|Italy|Spain|UK|USA|US|Canada|Australia|England|China|India|Japan|Brazil|Mexico))", 0.40),
        # City after "of" keyword — "of Mumbai", "of London", etc. (catches "the population of Mumbai")
        # Exclude common country names to avoid COUNTRY→CITY confusion
        ("CITY", r"(?i)\b(?:of|the\s+city\s+of)\s+(?!(?:Germany|France|Italy|Spain|UK|USA|US|Canada|Australia|England|China|India|Japan|Brazil|Mexico|Russia|Poland|Netherlands|Sweden|Norway|Denmark|Switzerland|Austria|Belgium|Ireland|Portugal|Turkey|Greece|Egypt|Thailand|Vietnam)\b)(?-i:[A-Z])[a-z]{2,}(?:\s+(?-i:[A-Z])[a-z]{2,})?\b", 0.40),

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
    ("COMPANY", r"\b(?:[A-Z][a-z]+)\s+(?:Technologies|Tech|Systems|Software|Solutions|Group|Partners|Holdings|Enterprises|Ventures|Industries|Global|International|Digital|Media|Networks|Services|Consulting|Associates|Motors|Airlines|Foods|Pharma|Bio|Labs|Works|Studios|Games|Health|Energy|Power|Capital|Finance|Insurance|Logistics|Transport|Retail|Electric|Chemical|Materials|Mining|Oil|Gas|Water|Telecom|Interactive|Cloud|Data|AI|Robotics|Research)\b", 0.55),

]