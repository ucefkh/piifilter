# Known Limitations

This document is an honest accounting of PIIFilter's shortcomings. We believe
transparency about failure modes is essential for responsible deployment. If you
rely on this tool for privacy guarantees, read this document carefully.

---

## 1. Token Split Vulnerabilities

PIIFilter's detection operates on individual tokens and chunks of text. When PII
is split across token boundaries — for example, a phone number like
`+1 555-123-4567` arriving as two separate chunks `+1 555-` and `123-4567` —
neither half matches a complete pattern, and the PII goes undetected.

**What this means in practice:**

- Streaming input (e.g., typing character by character in a chat interface)
  may see PII partially detected or missed entirely on the first pass
- Long prompts chunked by the upstream caller — PII may span chunk boundaries
- Tokenizer-split compound values like SSNs (`123-45-7890` split mid-hyphen)
  or credit cards (`4111-1111-1111-1111` split after a dash)

**Mitigation:** None at the pattern level. A post-hoc merge pass could
re-stitch adjacent fragments, but this is not currently implemented. For
batch/non-streaming input, the full prompt is visible at once and this is not
an issue.

---

## 2. Responsibility Gap — LLMs Can Infer PII from Context

PIIFilter replaces detected PII with aliases (e.g., `[PERSON_1]`), then sends
the aliased prompt to the LLM. The LLM may infer the original PII from
surrounding context, defeating the purpose of masking.

**Example:**

> Original: *"Alice is the CFO of Acme Corp, based in Berlin."*
> Aliased: *"[PERSON_1] is the CFO of [COMPANY_1], based in [CITY_1]."*

If the LLM already knows that Acme Corp is in Berlin and its CFO is Alice
Johnson (from training data, tool calls, or other context in the same session),
it may fill in the blanks and effectively "see" the PII anyway.

**What this means:**

- PIIFilter controls what leaves your machine, but cannot control what the LLM
  already knows or can deduce
- This is not a bug in the filter — it is a fundamental limitation of
  pseudonymization vs. anonymization
- For high-sensitivity use cases, consider combining PIIFilter with a) local
  models only (no data leaves your network) or b) output-side re-checking

---

## 3. Detection Gaps — Entity Recall and Precision Are Not Uniform

Regex patterns are the primary detection mechanism. Different entity types have
wildly different accuracy. The benchmark numbers below (from 184 entities across
24 types) tell the story:

| Entity Type       | Recall | Precision | Notes                                                        |
|-------------------|--------|-----------|--------------------------------------------------------------|
| API_KEY           | 1.00   | 0.91      | Reliable, but short keys may be missed if below length thresh|
| CREDIT_CARD       | 1.00   | 0.67      | 67% precision = 1 in 3 matches is a false positive           |
| DATABASE_URL      | 1.00   | 1.00      | Rock solid — distinctive format                              |
| DOMAIN            | 1.00   | 0.60      | False positives on any `word.word` string in prose           |
| EMAIL             | 1.00   | 0.86      | Reliable on standard formats                                 |
| FILE_PATH         | 1.00   | 0.93      | Reliable                                                     |
| GPS               | 0.55   | 0.80      | Lat/lon pair detection needs improvement; 45% recall gap     |
| IP_ADDRESS        | 1.00   | 0.93      | Reliable                                                     |
| JWT               | 0.89   | 1.00      | Reliable when present                                        |
| PASSPORT          | 1.00   | 1.00      | Reliable                                                     |
| PERSON            | 0.62   | 0.27      | **Major weakness** — 73% of flagged PERSON is wrong          |
| PHONE             | 0.96   | 0.63      | False positives on numeric sequences in prose                |
| PRIVATE_URL       | 1.00   | 0.93      | Reliable                                                     |
| PROJECT_NAME      | 0.94   | 1.00      | Good with context keywords                                   |
| SOCIAL_SECURITY   | 1.00   | 1.00      | Reliable                                                     |
| SSH_KEY           | 1.00   | 1.00      | Reliable                                                     |
| ADDRESS           | 0.86   | 0.67      | Context-dependent; misses non-standard address formats       |
| COMPANY           | 0.86   | 0.67      | Misses companies without Inc/LLC/Corp suffix                 |
| COUNTRY           | 1.00   | 0.86      | Good with keyword list                                       |
| CUSTOMER_NAME     | 0.33   | 0.50      | **Very weak** — needs NER model                              |
| EMPLOYEE_NAME     | 0.67   | 0.86      | Weak without role-prefix context                             |
| BANK_ACCOUNT      | 0.00   | —        | **Not detected** — entirely context-dependent                |
| CITY              | 0.00   | —        | **Not detected** — needs NER model                           |

**Key takeaways:**

- **PERSON** has 27% precision — most flagged "names" are false positives.
  This means 3 out of every 4 PERSON flags are wrong, which degrades user trust.
- **CITY** and **BANK_ACCOUNT** have zero recall — no regex pattern catches
  them reliably without surrounding context keywords.
- **CREDIT_CARD** and **DOMAIN** have precision around 0.60–0.67 — expect
  noticeable noise if you surface all detections to the user.
- **CUSTOMER_NAME** and **EMPLOYEE_NAME** are underpowered — they rely on
  narrow context phrases ("customer name is X") and miss everything else.

---

## 4. Encryption Is Not Masking

PIIFilter detects PII and replaces it with aliases **in flight**. It does not
encrypt the original text at any layer — the alias-to-original mapping lives in
an in-memory AliasStore (optionally persisted as unencrypted JSON).

**What this means:**

- Encryption (TLS, HTTPS, WSS) protects data **in transit** between your
  client, PIIFilter, and the LLM provider
- Encryption **does not mask PII in the prompt itself** — that is the job of
  the detection/replacement pipeline
- The alias store, if persisted to disk, contains the full mapping from
  aliases back to original values — anyone with filesystem access can read it
- There is no disk-level encryption on the alias store file

**Recommendation:** If you persist the alias store, encrypt the file at the
application level or store it on an encrypted filesystem. Use PIIFilter behind
a TLS-terminating reverse proxy for transport security.

---

## 5. Regex-Only Limitations — No Semantic Understanding

PIIFilter relies primarily on regex pattern matching (the `detector-regex`
plugin). Regex is inherently pattern-based, not semantic. This creates blind
spots:

**Context-dependent types that fool patterns:**

- A date like `"March 4, 1990"` is a valid birth date (PII). Without a
  context keyword like "DOB" or "birth" nearby, it looks like a plain date.
- A bare numeric sequence `"123456789012"` could be a bank account, a phone
  number extension, an order ID, or a random number — regex alone cannot
  disambiguate.
- Names that match common English words (`"Bill"`, `"Grace"`, `"Pat"`,
  `"Rose"`, `"Jack"`) trigger false positives or are missed depending on
  how the pattern is written.
- A single capitalized word at the start of a sentence — regex cannot tell
  if it is a name or the beginning of a sentence without NLP.

**Non-standard formatting:**

- Credit cards with unusual spacing or embedded text (`"card: 4111.1111.1111.1111"`)
- Phone numbers in non-Western formats (e.g., Japanese `080-XXXX-XXXX` without
  country code)
- Addresses not following `Number Street Suffix` structure (e.g., rural routes,
  PO boxes without "P.O. Box" phrasing, non-English address formats)

**Mitigation:** An NER-based plugin (`detector-gliner`) is planned but not yet
integrated. See `plugins/detector-gliner/` for current status.

---

## 6. Evasion Risks — Adversarial Input

A determined user can craft prompts that bypass PIIFilter's detection. Known
evasion vectors:

**Encoding tricks:**

- Base64-encoded PII — decoded values are never re-scanned
- URL-encoded strings (`%2B1%20555%2D1234`) — the encoded form may not match
  any pattern
- Unicode homoglyphs replacing ASCII digits (e.g., `４` instead of `4`)
- Hex-encoded or HTML-entity-encoded values

**Adversarial phrasing:**

- "My SSN is nine nine two, dash, one six, dash, seven eight nine zero" —
  spelled-out digits avoid numeric patterns entirely
- "My credit card is split across two lines: 4111-1111 / line break / 1111-1111"
- Injecting false delimiters or whitespace inside standard PII patterns

**Context manipulation:**

- Wrapping PII in code comments or markdown code blocks that the calling
  application strips before sending to the LLM (but after PIIFilter processes)
- Nested multi-byte encodings

**Current defense:** None. PIIFilter is not designed as an adversarial filter.
It assumes a cooperative or non-malicious user. If you face adversarial input,
you need a separate input sanitization layer above PIIFilter.

---

## 7. Non-English Language Limitations

PIIFilter's regex patterns are primarily designed for English and, to a lesser
extent, Latin-script European languages. Non-English detection is heuristic at
best.

**CJK (Chinese/Japanese/Korean):**

- PERSON detection has CJK-specific patterns (用户, 名前, 姓名 keywords) but
  these only fire when explicit context keywords are present
- Names written without a introducing keyword are missed entirely
- CITY detection in CJK text is zero — no CJK city-name patterns exist
- PHONE detection has CJK-aware patterns (电话), but formatting variance is
  high and misses are common

**Arabic:**

- Arabic-script PERSON patterns exist (اسم, اسمي keywords) but are narrow
- Arabic numerals are not distinguished from Latin digits — a 10-digit Arabic
  number could be flagged as PHONE when it is something else
- No address, city, or country patterns for Arabic-script text

**Cyrillic (Russian, Ukrainian, Bulgarian, etc.):**

- PERSON detection via contact/user context keywords targets Cyrillic names
  but with low recall
- No address or company patterns for Cyrillic text
- Phone patterns assume Latin digits

**Other scripts:**

- No detection support for Devanagari, Thai, Georgian, Armenian, Hebrew,
  or any other script not explicitly listed in patterns.py
- Non-script-specific patterns (SSN, credit card, IP, JWT, etc.) work
  regardless of surrounding script, but entity types requiring semantic
  understanding (PERSON, CITY, COMPANY, ADDRESS) are English/Latin-limited

---

## 8. Provider Reliability — Depends on the Local LLM

PIIFilter is designed to work with locally-hosted LLMs (LM Studio, vLLM) as a
privacy gateway. This dependency creates operational limitations:

**Current provider support:**

| Provider  | Status        | Streaming | Unfilter | Notes                              |
|-----------|---------------|-----------|----------|------------------------------------|
| LM Studio | ✅ Tested     | ✅ Working| ✅ Tested| Primary development target          |
| vLLM      | ✅ Implemented| ⚠️ Untested| ⚠️ Untested| Code present, not end-to-end tested |
| OpenAI    | ⚠️ Via middleware| ⚠️ Untested| ✅ Theoretical| Requires extra configuration     |

**Failure modes:**

- If the local LLM goes down (OOM, crash, model swap), PIIFilter has no
  automatic failover — requests fail
- Roundtrip tests (filter → LLM → unfilter) require a real running LLM;
  unit tests can mock this, but integration tests need infrastructure
- Streaming unfilter depends on the LLM's output format — if the provider
  changes its SSE schema or chunking behavior, the unfilter may break

**Recommendation:** Always run health checks on the upstream LLM before routing
traffic through PIIFilter. Monitor for provider-specific error codes.

---

## 9. Performance — Regex Scanning Cost on Long Prompts

Regex scanning is fast for typical use, but can become expensive on very long
or complex prompts.

**Measured performance (benchmarks as of July 2026):**

- Regex detection: <1ms per prompt (typical short prompts)
- Regex detection on large inputs (>100 KB): 10–50ms depending on pattern
  cardinality
- Presidio detection: 500–2000ms per prompt (model loading + inference)
- Pipeline overhead: ~10µs per prompt (event dispatch + merging)

**Scaling concerns:**

- Each prompt is scanned against ~80+ patterns (see `patterns.py`). Adding
  more entity types increases linear scan time.
- Backtracking in complex regexes (e.g., GPS coordinate patterns with
  optional groups) can cause catastrophic backtracking on pathological input.
  Current patterns are tested against this, but edge cases exist.
- The `unfilter_stream` method in `Session` buffers tokens with a configurable
  timeout (default 2 seconds). Very long aliases may cause latency spikes or
  premature flushing.

**Recommendation:** For latency-sensitive applications, use regex-only mode
(`detection.enabled_detectors: ["regex"]`). Avoid sending multi-megabyte
prompts through Presidio. Profile with your actual prompt payloads before
production deployment.

---

## 10. Streaming and Stateless Detection

The streaming detector processes tokens independently — it has no memory of
previous tokens in the stream. This introduces stateless-specific failure modes:

- **Partial-token false positives:** A stream fragment like `"4111-"` at the
  end of one chunk may trigger a false CREDIT_CARD match that is corrected
  when the next chunk arrives — but the correction may not reach the caller
  in time
- **Alias boundary confusion:** In streaming unfilter, if an alias
  (`[CREDIT_CARD_1]`) is split across two SSE data frames, the unfilter may
  output the raw alias text before enough context arrives to reverse it
- **Stateless detector** has no deduplication across stream — the same PII
  may be flagged multiple times as the stream progresses

These are architectural limitations of a pure streaming approach without
stateful buffering. A stateful streaming detector would add latency but
eliminate these edge cases.

---

## Summary: When Not to Use PIIFilter

PIIFilter is a **local-first privacy gateway for cooperative use cases**. It is
not:

- A security boundary against adversarial users
- An anonymization tool (it pseudonymizes, not anonymizes)
- A replacement for transport encryption (TLS)
- A compliance solution for GDPR, HIPAA, or similar regulations without
  additional audit and process controls
- A general-purpose PII redaction tool for binary, image, or audio content
- A multilingual solution for non-English-dominant workflows

Use it as part of a layered privacy strategy, not as the sole privacy
mechanism.

---

*Last updated: July 2026*