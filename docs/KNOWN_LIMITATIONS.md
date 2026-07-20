# Known Limitations

This document captures known limitations and gaps in PIIFilter's detection capabilities. These are not bugs — they are deliberate scope boundaries, unsolved problems, or tradeoffs we've accepted for performance/stability.

## Detection Gaps

### Entity Types

1. **DOMAIN_NAME**: Not implemented as a separate entity type. Domain names are detected as sub-components of `EMAIL`, `URL`, and `DATABASE_URL` matches. Standalone domain names (e.g., `example.com` without protocol or email context) are not flagged.

2. **ORGANIZATION / COMPANY / PERSON**: No ML/NER backend. All person/company/organization detection is regex-based and context-driven. This means:
   - Names without context keywords (`Name:`, `contact`, `regarding`) may be missed
   - Unusual name formats (hyphenated, initials-only) may not match
   - Ambiguous names like `Jordan` or `Paris` in isolation are not detected
   - Multi-word organizations without explicit structure (e.g., `The Foundation for Internet Development`) are not reliably captured

3. **ADDRESS** (International): Non-Western address formats (Japanese, Chinese, Arabic addressing conventions) have limited coverage. European-style addresses (number-after-street) have basic support.

4. **BANK_ACCOUNT**: Detection requires context keywords or long digit sequences (12+ digits). Short account numbers (8-11 digits) without context are not detected.

5. **PASSPORT**: Limited to Western alphanumeric formats (`AB1234567`). Non-Latin passport numbers and various national formats are not covered.

6. **PHONE**: International formats beyond E.164, US/UK/DE/FR patterns have partial coverage. CJK phone keywords are supported but format variations are extensive.

### Format-Specific Limitations

1. **Decimal GPS coordinates**: Individual decimal numbers (e.g., `40.7128`) have low matching confidence (0.55) to avoid FPs on non-GPS decimals. Pair matching is more reliable (0.88).

2. **CREDIT_CARD with non-standard separators**: Non-breaking spaces, mixed separators within the same number (dash + space), and unusual grouping patterns may not match.

3. **Masked values**: Detection confidence for masked values (e.g., `XXXX-XXXX-XXXX-1111`) is deliberately lower to avoid matching static placeholders.

### Performance Limitations

1. **Regex Explosion**: Some patterns use extensive negative lookaheads (especially PERSON patterns). Very long inputs with many capitalized words may trigger catastrophic backtracking. In practice this is rare for typical prompt-length text (<4K tokens).

2. **Overlapping Detections**: When multiple patterns match the same span at different confidences, only the highest-confidence match is kept. This is correct behavior but can mask secondary entity types.

## Architecture Limitations

1. **No NLP/NER Backend**: All detection is pattern-based. Entity types that require semantic understanding (PERSON, COMPANY, CITY, ADDRESS without keywords) will have lower recall than ML-based alternatives. This is a deliberate tradeoff for speed and offline capability.

2. **Language Coverage**: Non-Latin scripts (CJK, Cyrillic, Arabic) have keyword-triggered patterns but limited native coverage. Detection quality degrades for mixed-script or transliterated text.

3. **Context Window**: Detection operates per-text-call with no cross-message state. Entity types detected from conversational context spanning multiple messages are not supported.

4. **No Entity Resolution**: The same entity mentioned multiple times is detected each time independently. There is no deduplication or canonicalization across occurrences.

## Testing Coverage Gaps

1. **Golden Corpus**: The golden corpus at `benchmarks/data/golden_corpus.json` contains 257 examples covering 25 entity types, but:
   - Some entity types have minimal coverage (3-5 examples)
   - Annotation quality varies — spans and values may not perfectly align due to historical corpus construction
   - Negative examples (texts with no PII) are limited

2. **Fuzz Testing**: Hypothesis-based property tests run on every commit but use deterministic seeds. Edge cases not covered by the seeded strategy may be missed.

3. **Integration Tests**: Integration tests in `tests/integration/` require external services (Inference Gateway) and are excluded from CI by default.

## Future Work

See [ROADMAP.md](../ROADMAP.md) for planned improvements.