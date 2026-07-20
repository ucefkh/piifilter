# Known Limitations

This document captures known limitations, edge cases, and design trade-offs in PIIFilter's regex-based detector. It is a living document — update it as new limitations are discovered or existing ones are resolved.

## Detection Engine Limitations

### 1. Inner-Separator Stripping Destroys Some Patterns

The deobfuscation pipeline strips inner separators (dots, dashes, slashes, commas, NBSP) from text before running structural patterns. This is critical for catching obfuscated SSNs (`123-45-6789` → `123456789`), credit cards (`4111-1111-1111-1111` → `4111111111111111`), and API keys. However, it destroys patterns that *need* those separators:

- **GPS coordinates** (`40.7128, -74.0060` → `407128-740060`) — GPS patterns are run **pre-strip** as a workaround.
- **Dotted-decimal IPs** (`192.168.1.1` → `19216811`) — IP patterns are run **pre-strip** as a workaround.
- **Dates** (`2024-01-15`, `12/31/2025`) — DATE patterns are run **pre-strip** as a workaround.
- **CJK phone numbers** (`电话 +86 138-0013-8000`) — CJK phone patterns are run **pre-strip** as a workaround.
- **European addresses** (`Unter den Linden 1, 10117 Berlin`) — ADDRESS patterns are run **pre-strip** as a workaround.

**Impact**: Pre-strip patterns use original-text coordinates while stripped patterns use cleaned coordinates. Cross-type deduplication must use value-based (not position-based) matching, which is less precise.

### 2. Pre-Strip / Post-Strip Coordinate Mismatch

Entities detected on pre-strip text (GPS, DATE, IP, PHONE-CJK, ADDRESS, PRIVATE_URL) use original-text character offsets. Entities detected on stripped text use cleaned-text offsets. When these are merged, same-type dedup uses value-based comparison which can fail on:

- Entities whose values partially overlap in text but not in digit-content
- Entities whose values change due to NFKC normalization (e.g. fullwidth digits → ASCII)

### 3. Ambiguous Digit Runs

Continuous digit runs that happen to match SSN, CC, or phone patterns after stripping are inherently ambiguous:

- **9-digit runs** that pass the SSN validator (area/group/serial checks) may still be IP addresses, phone numbers, or other identifiers that happen to be 9 digits. Cross-type dedup with pre-strip IP/GPS/DATE entities catches many but not all of these.
- **13-19 digit runs** that pass the Luhn check may be bank account numbers, order IDs, or transaction references. The Luhn gate is algorithmic but not perfect — some valid cards may be missed if the check digit doesn't pass, and some non-card numbers may pass.

### 4. Confidence Scoring Is Heuristic

Confidence scores (0.0–1.0) are assigned per-pattern based on heuristics (specificity, context keywords, structural validation). These scores are not calibrated against real-world data:

- A score of 0.95 does not mean "95% likely correct" — it means "this is a very specific pattern with low FP risk."
- Thresholds in `benchmark_runner.py` balance recall vs. precision per entity type, but optimal thresholds depend on the use case.
- The balanced mode uses thresholds that work well on the golden corpus but may need tuning for your data.

### 5. IBAN / CREDIT_CARD Ambiguity

IBAN substrings can look like credit card numbers. For example, `6016 1331 9268 19` (part of `GB29 NWBK 6016 1331 9268 19`) matches the 4-4-4-4 CC pattern. Current mitigation:

- IBAN patterns are ordered **before** CC patterns in `patterns.py`
- CC patterns have negative lookbehinds for IBAN-like prefixes (`(?<![A-Z0-9]{4}\s)`)
- The dedup logic skips detections contained within already-matched intervals

**Remaining gap**: If an IBAN appears in a format not caught by the lookbehind, or the IBAN detection itself fails (too short, wrong country code format), the CC FP may leak through.

### 6. PERSON False Positives from Technical Terms

The PERSON entity type uses context keywords and capitalized-word heuristics. This can produce false positives on:

- **Technical role words** like `Postgres`, `Admin`, `Root`, `Config`, `Settings` — mitigated by a denylist in person patterns, but new terms may slip through.
- **Two-word capitalized phrases** that aren't names (e.g. `Support Team`, `Security Access`, `Profile Settings`).
- **Email local-parts** with capitalized segments before the `@` — caught by EMAIL type first, but context-pattern PERSON matches can overlap.

### 7. COMPANY Two-Capitalized-Word False Positives

The low-confidence COMPANY pattern that matches two capitalized words (`[A-Z][a-z]+ [A-Z][a-z]+`) is inherently prone to FPs on:

- Person names (Alice Smith)
- Project names (Project Phoenix)
- Geographic names (New York)
- Technical terms (Config Manager)

Mitigations: restricting to company-suffix words or context keywords before the match. Still produces FPs in ambiguous contexts.

### 8. GPS Decimal-Only Matching

Bare decimal numbers (e.g. `3.14159`, `1.234`, `0.5678`) are no longer matched as GPS coordinates — this was fixed by requiring GPS context keywords (`lat`, `lon`, `coordinates`, `gps`, etc.) for single-value decimal matches.

**Remaining gap**: A decimal that happens to follow a GPS keyword in non-GPS context (e.g. "check the lat setting: 3.14159") would still match.

### 9. PHONE CJK Truncation

Phone numbers after CJK keywords (`电话`, `電話`, `手機`) can be truncated if the CJK pattern's character class doesn't account for all Unicode dash or space variants. The current patterns use `[\s–—−\-]+` to handle multiple separator types, but edge cases with mixed-width characters or unusual spacing may cause partial matches.

### 10. Masked Entity Detection Is Heuristic

Masked/redacted entities (MASKED_SSN, MASKED_CC) are detected with low confidence (0.45–0.70) and are often:

- Too broad: `XXX-XX-XXXX`-like patterns match teaching examples and fictional data
- Too narrow: Non-standard mask formats (e.g. `***-**-****`) use different mask characters and may be missed
- Context-dependent: These patterns rely on SSN/credit-card keywords for higher confidence, so a masked number without context may be at FP-risk threshold

### 11. LANGUAGE_COUNTRY Ambiguity

Country names that are also language names (e.g. `German`, `English`, `French`) are matched by the COUNTRY entity type. This is correct when the word refers to the country, but the current patterns have no way to distinguish "German" (the language) from "German" (the person from Germany). The BALANCED mode threshold (0.50) lets these through; higher thresholds filter them out.

### 12. Deobfuscation Limitations

The deobfuscator handles:
- NFKC normalization (fullwidth → ASCII, ligatures → base chars)
- [at] → @, [dot] → . replacement
- HTML entities (`&#x40;` → `@`)
- Zero-width character removal
- Unicode escape sequences (`\u0040` → `@`)

It does NOT handle:
- Caesar/ROT13 obfuscation
- Reversed strings
- Character substitution ciphers (e.g. `4` for `A`, `3` for `E`)
- Morse code or other encoding schemes
- Split-PII across multiple fields (e.g. SSN in two separate form fields)

## Benchmark Limitations

### 1. Golden Corpus Coverage

The golden corpus contains 316 annotated entities across 28 types. While diverse, coverage per type is uneven:

- Well-covered: CITY (30), COMPANY (25), COUNTRY (27), CREDIT_CARD (17), EMAIL (17), GPS (18), PERSON (18), PHONE (15), PRIVATE_URL (12), ADDRESS (11), IP_ADDRESS (11)
- Poorly covered: DOMAIN (4), JWT (5), PROJECT_NAME (6), MASKED_SSN (0), MASKED_CC (0)

Low-count types may have hidden regressions that only appear with more data.

### 2. No Real-World PII

The golden corpus uses synthetic PII — plausible-looking but not real personal data. This means:
- No testing against real-world obfuscation patterns
- No testing against edge cases from production traffic
- All entity values are contrived examples

### 3. No Cross-Entity Interaction Stress Testing

The benchmark evaluates each entity in isolation (single annotation per example). It does not stress-test the detector's dedup, overlapped-entity resolution, or priority logic with multiple overlapping annotations in the same text.

## Known Not-Addressed Issues

- **MASKED_SSN and MASKED_CC have no golden corpus labels** — these entity types exist in the pattern set but have zero benchmark entries, so FPs or FNs in masked entity detection are invisible to the eval.
- **CITY in parentheses after GPS** — Some CITY entities appear in parentheses after GPS coordinates (e.g. `(London)` after lat/lon). These are labeled as CITY in the corpus but may be undesirable in production. Currently mitigated by selective lookbehinds for high-precision modes.