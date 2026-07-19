# Known Limitations

This document honestly describes the current limitations of PIIFilter v2. We believe
transparency about failure modes is essential for responsible deployment.

## 1. Semantic Entity Detection

### Person, Company, City, Country — Regex-only is insufficient

PIIFilter currently uses regex patterns for PERSON, COMPANY, CITY, COUNTRY and similar
semantic entity types. Regex can only approximate these with:
- Honorific-prefixed names (Mr. Smith, Dr. Jones)
- Context phrases ("my name is X", "our CEO Y")
- Keyword lists (company suffixes, country names)

**What this means:**
- Non-Western names (CJK, Arabic, Cyrillic) are **not detected** by regex
- Simple "First Last" names without context prefixes are **missed**
- City names in running text without state/zip context are **missed**
- Company names without Inc/LLC/Corp suffixes are **missed**

**Planned fix:** Integration of GLiNER or a small NER model for semantic entity detection.
See `plugins/detector-gliner/`.

### Names in aliasing contexts

When the user says "Alice" without "my name is" or "Dr." prefix, regex will not
detect it as PERSON. The same applies to any unmarked proper noun.

## 2. Numeric Type Confusion

### Bank Account vs Credit Card vs Phone vs Passport

Bare digit sequences are inherently ambiguous. PIIFilter uses context-keyword
patterns ("bank:", "credit card:", "phone:", "passport:") and a fallback score system:

- Context-matched patterns: score 0.85–0.90
- Context-free bare-digit patterns: score 0.65–0.75

**What this means:**
- Numbers without surrounding context may be misclassified (e.g., "123456789012" as
  PHONE instead of BANK_ACCOUNT)
- Adding context keywords improves classification significantly

## 3. Token Splitting in Streaming Unfilter

The `unfilter_stream` method in `Session` buffers tokens at alias boundaries. When
an alias spans multiple tokens, the system buffers up to a configurable timeout
(default 2 seconds) before flushing.

**Potential issues:**
- Very long aliases may cause latency spikes
- If an alias is split across multiple LLM output chunks in a slow stream,
  the buffer timeout may fire before the complete alias is received
- The timeout is global — not adaptive to stream velocity

## 4. Presidio Integration

### False Positive Rate

Presidio's NER engine produces false positives on generic text:
- LOCATION: Flags common nouns, city names in isolation
- PERSON: Flags any capitalized name-like token
- DATE_TIME: Was previously mapped to PERSON (fixed in v0.1.0)

The current mitigation is a score threshold (≥0.75) and removing low-precision
entity mappings. This reduces recall but keeps precision manageable.

**What this means:**
- Presidio contributes primarily to PERSON and CREDIT_CARD detection
- ADDRESS and LOCATION detection is currently handled by regex patterns only
  (LOCATION was removed from presidio mapping due to excessive false positives)

## 5. Encryption

PIIFilter does **not** encrypt PII data at rest or in transit. It operates as a
transparent proxy:
- PII is detected, replaced with aliases, and forwarded to the LLM
- The alias-to-original mapping is stored in memory (AliasStore)
- Persistent alias stores (JSON-based) are unencrypted

**Recommendation:** Use PIIFilter with encrypted transport (HTTPS/WSS) and
encrypt the alias store at the application level if persistence is needed.

## 6. LLM Provider Compatibility

### Provider Support Matrix

| Provider | Status | Streaming | Unfilter |
| -------- | ------ | --------- | -------- |
| LM Studio | ✅ Tested | ✅ Working | ✅ Tested |
| vLLM | ✅ Implemented | ⚠️ Untested | ⚠️ Untested |
| OpenAI | ⚠️ Via middleware | ⚠️ Untested | ✅ Theoretical |

### Streaming

The OpenAI-compatible streaming API is supported via SSE parsing. The unfilter
stream correctly reverses aliases in real-time output. However, the roundtrip
test requires a real LLM running locally.

## 7. Detection Accuracy

### Benchmark (as of July 2026)

PIIFilter achieves the following detection recall/precision on the benchmark dataset
(122 examples, 184 entities, 24 types):

| Entity Type | Recall | Precision | Notes |
| ----------- | ------ | --------- | ----- |
| API_KEY | 1.00 | 0.91 | Reliable |
| CREDIT_CARD | 1.00 | 0.67 | Context-dependent |
| DATABASE_URL | 1.00 | 1.00 | Rock solid |
| DOMAIN | 1.00 | 0.60 | False positives on internal URLs |
| EMAIL | 1.00 | 0.86 | Reliable |
| FILE_PATH | 1.00 | 0.93 | Reliable |
| GPS | 0.55 | 0.80 | Lat/lon pair detection needs improvement |
| IP_ADDRESS | 1.00 | 0.93 | Reliable |
| JWT | 0.89 | 1.00 | Reliable |
| PASSPORT | 1.00 | 1.00 | Reliable |
| PERSON | 0.62 | 0.27 | Needs NER model |
| PHONE | 0.96 | 0.63 | False positives on bare digits |
| PRIVATE_URL | 1.00 | 0.93 | Reliable |
| PROJECT_NAME | 0.94 | 1.00 | Good with context |
| SOCIAL_SECURITY | 1.00 | 1.00 | Reliable |
| SSH_KEY | 1.00 | 1.00 | Reliable |
| ADDRESS | 0.86 | 0.67 | Context-dependent |
| COMPANY | 0.86 | 0.67 | Limited by regex |
| COUNTRY | 1.00 | 0.86 | Good with keyword list |
| CUSTOMER_NAME | 0.33 | 0.50 | Weak — needs NER |
| EMPLOYEE_NAME | 0.67 | 0.86 | Weak — needs NER |
| BANK_ACCOUNT | 0.00 | — | Missed — context-dependent |
| CITY | 0.00 | — | Needs NER model |

## 8. Data Format Limitations

- **Only text input** — images, audio, and binary attachments are not scanned
- **Basic text wrapping** — PDF, DOCX, or HTML formatting is not parsed
- **The streaming detector** is stateless — tokens are processed independently
  and can trigger false positives on partial content

## 9. Performance

- **Regex detection**: <1ms per prompt (lightning fast)
- **Presidio detection**: 500–2000ms per prompt (model loading + inference)
- **Pipeline overhead**: ~10µs per prompt (event dispatch + merging)

Presidio is the bottleneck. For latency-sensitive applications, consider using
regex-only mode by setting `detection.enabled_detectors: ["regex"]`.

---

*Last updated: July 2026*