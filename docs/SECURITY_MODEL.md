# PIIFilter Security Model

## Threat Model
PIIFilter protects personally identifiable information (PII) from being sent to Large Language Models (LLMs). The PII is detected and replaced with non-identifying aliases before reaching the LLM. After the LLM responds, the aliases are restored to their original values.

## What PIIFilter Protects Against
- **Accidental PII leakage via LLM prompts**: Users who paste text containing PII into AI tools
- **PII in training data**: PII is never sent to the LLM provider's servers in original form
- **Casual inspection**: Intercepted prompts don't contain raw PII

## What PIIFilter Does NOT Protect Against
- **Side-channel attacks**: Timing, token count, or response patterns that leak information
- **LLM inference attacks**: A hostile LLM cannot reconstruct original PII from aliases (aliases are deterministic pseudonyms with no semantic relationship to the original)
- **Disk compromise**: The SQLite AliasStore is encrypted at rest only when `PIIFILTER_STORE_KEY` is set

## Recall Floor
PIIFilter targets a **recall ≥ 0.95** for every supported entity type on naturally-occurring text. Entity types falling below this threshold are documented in `KNOWN_LIMITATIONS.md` and actively tracked for pattern improvements.

## Metric: F-beta with β=2
We use F-beta (β=2) rather than F1 to weight recall 2x over precision. A PII leak (false negative) is more harmful than a false positive. Reported as F2 score.

## Adversarial Evasion
PIIFilter does **not** currently protect against deliberately obfuscated PII (homoglyphs, base64 encoding, zero-width characters, split across conversation turns). This is a known limitation.