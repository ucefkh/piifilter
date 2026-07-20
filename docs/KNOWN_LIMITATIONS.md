# Known Limitations

This document catalogs known limitations and edge cases in PIIFilter that are
understood but not yet addressed. Each entry explains the limitation, why it
exists, and the workaround (if any).

---

## 1. CREDIT_CARD: Duplicate bare-digit detections in raw mode

**Status:** Known, mitigated by arbitration

When a credit card number appears in formatted form (e.g. `4111-1111-1111-1111`),
the deobfuscation pipeline strips inner separators (dashes, spaces), producing
`4111111111111111`. Both the formatted pattern and the bare-digit patterns
(`\b\d{16}\b`, `\b\d{13,19}\b`, `\b(?:4\d{3}|...)\d{12}\b`) may fire,
creating duplicate entities with different span positions. The arbitration layer
deduplicates these; raw detection can produce up to 5 extra FPs on a 7-entity
benchmark set.

**Workaround:** None needed — arbitration handles it.

---

## 2. PHONE: CJK-prefixed phones may have truncated spans

**Status:** Unfixed

CJK phone patterns (prefixed by 电话/電話) may capture slightly different spans
than the expected phone number when processed through the deobfuscation/stripping
pipeline. This affects span-based matching in the benchmark but not detection
correctness.

---

## 3. DOMAIN: Short uppercase patterns structurally matching domain regex

**Status:** Fixed in 841ac8a

Short text patterns like `:A.AA` and `AA.AA` structurally match the DOMAIN
regex `[a-zA-Z0-9-]+\.[a-zA-Z]{2,}\b` but are not real domain names. Fixed
by requiring the first label to be >= 2 characters for the brand-domain bypass.

---

## 4. IBAN: CREDIT_CARD false positives from IBAN trailing segments

**Status:** Partially mitigated

IBAN trailing digit groups (e.g. `0044 0532 0130 00` within the German IBAN
`DE89 3704 0044 0532 0130 00`) can match CREDIT_CARD 4-4-4-N patterns via
Luhn validation. IBAN patterns are defined before CREDIT_CARD in the pattern
list, and the containment dedup suppresses CC matches inside IBAN spans. This
works for correctly-formed IBANs but may miss edge cases where the IBAN
pattern fails to match.

---

## 5. IP_ADDRESS: Decimal IP catch-all produces FPs on dates and SSNs

**Status:** Partially mitigated

The decimal IP catch-all pattern (score 0.65) matches any 7-10 digit number
that decodes to a valid IPv4 address (32-bit unsigned integer 16777216–
4294967295). This catches obfuscated IPs formatted as decimal numbers but
also matches 9-digit SSNs and 8-digit dates (e.g. `12312025`) that happen
to decode to valid IPs. Anti-FP heuristics suppress SSN-looking and SSN-
context numbers.

---

## 6. COMPANY: Two-capital-word company name FPs

**Status:** Partially mitigated

Two-capital-word patterns (e.g. `Bob Smith`) are matched both as PERSON and
COMPANY. COMPANY patterns with score 0.55 use context keywords ("works at",
"Invoice from", "Signed by") to reduce FPs, but some ambiguous phrases
still produce cross-type duplicates.

---

## 7. GPS: Decimal-only coordinates not matched

**Status:** Unfixed

GPS patterns require explicit degrees/minutes/seconds format or DDM format.
Pure decimal degree strings without N/S/E/W indicators or "lat/lng" keywords
are not detected.

---

## 8. PHONE: URL-encoded phone numbers produce span mismatches

**Status:** Known

URL-encoded phone numbers (e.g. `%2B1-555-123-4567`) are decoded by the
deobfuscator to `+1-555-123-4567`, which is correctly detected. However,
the span positions on the original encoded text differ from the deobfuscated
text, causing benchmark matching mismatches.

---

## 9. CITY: High false positive rate without context gate (heldout)

**Status:** Gated by default

The CITY detector matched 22 false positives in the heldout adversarial set
without the context gate (precision 0.2903). The context gate (disabled by
default) improves precision to 0.924 but may miss some legitimate city names.

---

## 10. SSN: Area 900-999 blocking catches valid SSNs from recent allocations

**Status:** Known trade-off

The SSN area 900-999 range has been historically unassigned but SSA has
begun allocating areas in the 900s. The current blocker (area >= 900 →
not valid SSN) may false-negative legitimate SSNs from these new allocations.

---

## 11. EMAIL: Unicode email addresses not fully supported

**Status:** Known

Full international email (EAI/RFC 6531) with non-ASCII characters in the
domain part is not detected. Only ASCII domains with ASCII local-parts
are matched by the EMAIL patterns.

---

## 12. Roundtrip: No end-to-end unfilter roundtrip test against real models

**Status:** Unfixed

There is no automated test that sends PII-containing prompts through the
full pipeline (detect → mask → LLM → unmask) against a real model endpoint
(Ollama, OpenAI, etc.). Unit tests cover individual components but the
integrated flow is only manually verified.