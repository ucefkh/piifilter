# PIIFilter Known Limitations

This is an honest accounting of failure modes found in the actual source
code (`patterns.py`, `alias_store_persistent.py`, `session.py`, etc.).
If you rely on PIIFilter for privacy guarantees, read this carefully.

---

## Detection

### CREDIT_CARD / IBAN overlap

IBAN numbers (`DE44 5001 0517 5407 3249 31`) contain digit-group sequences
that structurally resemble credit card 4-4-4-4 formats. The regex
explicitly uses negative lookbehinds `(?<![A-Z]{2}\d{2}\s)` and negative
lookaheads `(?![ -\d{2,4}])` to avoid this, but:

- IBANs with non-standard spacing or missing country-code prefixes can bypass
  the lookbehind and get flagged as `CREDIT_CARD`.
- The reverse (credit card caught as IBAN) is also possible since IBAN
  accepts `[A-Z]{2}\d{2}(...){4,7}`.
- **In practice:** expect 1-2% false crossover on mixed financial data.

### CJK phone numbers may be truncated

The CJK phone patterns (lines 77-79 of `patterns.py`) require a keyword
prefix like `电话` or `電話は`. When a phone appears in CJK context
*without* an explicit keyword — e.g. as part of a contact card or a
standalone `+86 138-0013-8000` — the keyword-based regex doesn't fire.

Even when the keyword is present, the regex captures everything after it
with `[\d-]+`, which can swallow trailing punctuation or absorb space-
separated digit groups from subsequent text.

### GPS single decimal coordinates

The line 102 pattern `(?<!\d)(?<!\d\.)[-+]?\d{1,2}\.\d{4,}(?!\d)` at 0.70
confidence matches **any** number with 4+ decimal places. This means:

- Timestamps like `1.2345s` get flagged as GPS.
- Version numbers like `2.71828` get flagged as GPS.
- Any scientific decimal → false positive.

The only guard is the 0.70 confidence threshold; there is no semantic
verification (no check for lat/lng range validity 0-90 / 0-180).

### COMPANY vs CITY confusion

Both entity types match two-capitalized-word patterns at low confidence:

- `COMPANY` (line 207): matches `Word Technologies|Systems|Solutions|...`
- `CITY` (lines 183-186): matches `based in CityName` or `in CityName`

A phrase like *"based in Quantum Systems"* can trigger **both** CITY
(via "based in") and COMPANY (via "Systems" keyword). The deduplication
in the pipeline picks whichever detector runs first, which is non-
deterministic from the user's perspective.

### PERSON false positives on technical terms

The `user:` pattern (line 137) explicitly excludes `admin|root|postgres|...`
but any other capitalized technical label triggers a match:

- `User: Guest` → PERSON match (Guest is a common but also a technical
  account name)
- `User: Alfred` → PERSON match (correct, but indistinguishable from
  `User: Postgresql` if Postgresql weren't explicitly blacklisted)
- Single-word names at sentence start are invisible to PERSON patterns
  (they need a title prefix or context keyword), so *"Jane walked in"*
  is never detected.

---

## Unfilter (alias restoration)

### Token boundary splits in streaming

The `unfilter_stream` method in `session.py` buffers tokens and checks
for partial alias prefixes. Failure modes:

- **Alias split across SSE frames**: If `[PERSON_1]` arrives as
  `[PERSON_` and `1]` in separate chunks, the buffer builds up until
  either the full alias appears or the 2-second timeout fires. On
  timeout, the raw partial alias text (`[PERSON_`) is emitted verbatim.
- **Nested aliases in same buffer**: If two aliases arrive in the same
  chunk (`[PERSON_1] [COMPANY_2]`), only the first match is consumed
  per iteration; the second alias's prefix may sit in the buffer and
  trigger a premature timeout flush.
- **Alias sorting**: Aliases are sorted by length descending. If a
  shorter alias is a prefix of a longer one, the shorter is checked
  first; if it's in the buffer but not at the tail, it's missed.

### Paraphrasing defeats unfilter

The unfilter is a **string-replacement** pass. If the LLM rewords:

- `[PERSON_1]` → `"the individual"` or `"the first person mentioned"`
- `[COMPANY_1]` → `"that organization"` or `"the client"`

…the original is permanently lost. The unfilter cannot reason about
aliases; it only scans for exact string matches.

### No unfilter without AliasStore

If `alias_store` is None or `conversation_id` is unset (line 169 of
`session.py`), the streaming unfilter returns immediately with a
passthrough — the LLM response contains raw alias tokens like
`[PERSON_1]` with no restoration.

### Case sensitivity

`replace_in_response` (line 130 of `session.py`) uses `str.replace`
which is case-sensitive. An LLM that outputs `[person_1]` instead of
`[PERSON_1]` will leave it unreplaced. The alias store itself is also
case-sensitive — `"Alice"` and `"alice"` are separate entries.

---

## Encryption (SQLite backend)

### Fernet key is optional

When `PIIFILTER_STORE_KEY` env var is unset (the default), the
`SQLiteAliasBackend` stores plaintext (lines 165-168 of
`alias_store_persistent.py`). The `_encrypt`/`_decrypt` helpers
return the input unchanged when `fernet is None`.

This is **by design** for testability, but can catch operators off
guard: persistence is always on when SQLite is used, but encryption
is opt-in.

### Hardcoded PBKDF2 salt

Line 42: `FERNET_SALT = b"piifilter_alias_store_salt_v1"`

The salt is a compile-time constant, not user-configurable. This means:

- All PIIFilter deployments that use `PIIFILTER_STORE_KEY` derive
  their key from the same salt → pre-computed rainbow tables against
  the PBKDF2 output are theoretically possible.
- Key rotation (changing `PIIFILTER_STORE_KEY`) requires a manual
  migration: re-encrypt every row with the new key. No automated
  re-keying exists.

### Deterministic lookup hash leaks entropy

The `lookup_key` column stores SHA-256(plaintext). An attacker with
DB read access can:

- Hash common names, emails, SSNs and compare against `lookup_key` to
  identify which rows contain specific values (confirmation attack).
- Since the original value is also encrypted in the same row, a matched
  lookup_key + brute-force of weak passphrases → plaintext recovery.

### No cleanup on `__init__` failure

If `_init_db()` succeeds but `_make_fernet()` raises (bad env var?), the
table is left in an inconsistent state — the DB file is created but the
connection is never used.

---

## General

### Detectors run independently; no cross-detector consistency

The pipeline's `_detect` method (line 102-151 of `pipeline/__init__.py`)
runs each detector on the full prompt independently and deduplicates by
span. It does **not** check whether two overlapping entities of different
types make semantic sense — e.g., a span detected as both `PERSON` and
`COMPANY` at different positions isn't cross-validated.

### Regex patterns are English/Latin-centric

Non-English PII:
- CJK names need explicit keywords (`用户`, `名前`); standalone CJK
  names in prose are invisible.
- Arabic names (lines 143-144) need `اسم`/`اسمي` keyword prefix.
- Cyrillic (line 141) needs `contact is Name` English wrapper.
- Devanagari, Thai, Hebrew, Armenian: zero coverage.

### Streaming alias buffering uses fixed 2s timeout

The `timeout` parameter in `unfilter_stream` (line 152) is configurable
but defaults to 2 seconds. If the LLM takes longer to emit the rest of
an alias token (slow generation, high latency), the buffer flushes raw
text with a partial alias exposed.

### No rate limiting or auth on the REST API

There is no authentication layer, rate limit, or request budget. Any
client that reaches the PIIFilter HTTP endpoint can process prompts.
This is acceptable for local-only deployments but unsafe if exposed
(even behind a VPN).

### On-error fallback exposes `[PIIFilter Error: ...]`

Line 272 of `pipeline/__init__.py`: when the provider fails, the error
message is embedded directly into `llm_response`:

```python
session.llm_response = f"[PIIFilter Error: {exc}]"
```

This may leak internal state (file paths, connection strings, stack
traces) to the caller.

---

## Summary: When Not to Use PIIFilter

- Against adversarial prompt injection — no evasion defense exists
- For true anonymization — it pseudonymizes, not anonymizes
- As a compliance sole-mechanism (GDPR, HIPAA) — needs audit + process
- For binary/image/audio PII — text-only detection
- For non-English-dominant workflows — English/Latin bias in patterns