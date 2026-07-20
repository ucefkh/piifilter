# Known Limitations

This document catalogs known limitations, edge cases, and false-positive/negative patterns in PIIFilter's regex-based detector. It is intended for developers and maintainers.

## Table of Contents

- [Detection Limitations](#detection-limitations)
- [False Positives](#false-positives)
- [Deobfuscator Limitations](#deobfuscator-limitations)
- [Benchmark Limitations](#benchmark-limitations)

## Detection Limitations

### EMAIL

| Issue | Details |
|-------|---------|
| Zero-width chars in email | Emails like `joh\u200dn@example.com` are reconstructed by the deobfuscator to `john@example.com`, but the span positions shift, causing a benchmark false-negative because the expected value is the original obfuscated form. |
| URL-encoded emails | `john%40example.com` is deobfuscated to `john@example.com` but span mismatch causes benchmark FN. |
| HTML entity emails | `john&#64;example&#46;com` deobfuscated to `john@example.com` — same span issue. |
| JSON escaped emails | `john\\u0040example\\u002Ecom` deobfuscated correctly, span mismatch. |
| Full-width emails | `ａｌｉｃｅ＠ａｃｍｅ．ｃｏｍ` deobfuscated via NFKC but span positions differ. |
| Token-split emails | `"john" + "@" + "example.com"` — the reconstructed concatenation has different positions than the original labeled entity. |

Recovery: The benchmark should match against the deobfuscated text, or the detector should report both raw and deobfuscated spans.

### PHONE

| Issue | Details |
|-------|---------|
| Cyrillic homoglyph digits | `+1-555-123-4Ӧ97` where `Ӧ` (U+04E6) visually resembles `5`. The deobfuscator has no Cyrillic→Latin digit mapping, so this phone is missed. |
| Negative context phrases | `"not a real phone"` preceding a phone-like number (e.g., `123-456-7890`) produces a false positive. |
| Spaced bare digits on stripped text | After _strip_non_alpha_seps, phone-like digit sequences from stripped IPs can match phone patterns (e.g., 10-digit remain of a dotted IP). Partially mitigated by `_filter_phone_overlap`. |

### GPS

| Issue | Details |
|-------|---------|
| Decimal-only FPs | Standalone decimal numbers (e.g., `192.168` from `192.168.x.x` notation) can be caught by the catch-all GPS pattern. |
| Keyword-prefixed coordinates | Coordinates labeled with `lat:`/`lon:` keywords that the benchmark doesn't tag as GPS appear as false positives, but are correct detections. |

### PERSON

| Issue | Details |
|-------|---------|
| Arabic `اتصل بـ` prefix | The Arabic phrase `اتصل بـ أحمد` (call Ahmed) matches a PERSON pattern that includes the `بـ` prefix, producing a FP span. |
| CJK user context | `用户张伟` (user Zhang Wei) is detected as PERSON, which is correct but the benchmark doesn't always label it. |
| Cyrillic names | `O Γιώργος` (Greek "the George") and Russian names are detected but may not be benchmarked. |

### SOCIAL_SECURITY

| Issue | Details |
|-------|---------|
| Masked SSNs | Partially redacted SSNs like `***-**-6789` are detected but may be suppressed if the digit portion is too short. |
| IP→SSN residue | After inner-separator stripping, a dotted IP like `192.168.1.50` becomes `192168150` — a 9-digit string that passes SSN validation. Mitigated by `_filter_ssn_overlap`. |

### URL

| Issue | Details |
|-------|---------|
| No URL entities in dataset | The benchmark dataset has 0 expected URL entities. The 3 false positives (`http://127001/api/health`, `www.example.com`, `https://example.com/api`) are actually reasonable detections that should likely be labeled as URL or DOMAIN. |

### CREDIT_CARD

| Issue | Details |
|-------|---------|
| IBAN trailing segments | IBAN trailing digit segments (e.g., `6016 1331 9268 19`) can look like 4-4-4-2 CC patterns. Mitigated by placing IBAN patterns before CC patterns and using the `(?<![A-Z]{2}\\d{2}\\s)` lookbehind on CC patterns. |
| Luhn gate FP/FN | The Luhn validation gate eliminates ~99% of random 16-digit FPs, but some Luhn-valid non-CC numbers (like certain IBANs) can still pass. |

### COMPANY

| Issue | Details |
|-------|---------|
| Context-prefixed matches | `works at Microsoft Research` includes the `works at ` prefix in the match because the pattern uses a keyword prefix. The dedup logic prefers narrower same-type matches, but if the narrower pattern fires first, the broader match is preserved. |
| Single-word company names | The explicit-known-companies list (line 484) covers ~150 well-known brands. Smaller or less-known companies may be missed without keyword context. |

## False Positives

These entity types have precision < 0.95 on the benchmark dataset (regex detector):

| Type | Precision | Known FP patterns |
|------|-----------|-------------------|
| SOCIAL_SECURITY | 0.9333 | Masked SSN `***-**-6789` detected without full digit content |
| PERSON | 0.9474 | Arabic `اتصل بـ` prefix match |
| PHONE | 0.9032 | Negative-context phones (`not a real phone`), bare-digit stripped-IP residue |
| IP_ADDRESS | 0.9032 | Version numbers, dates with dot separators passing through pre-strip guards |
| PRIVATE_URL | 0.9333 | DATABASE_URL→PRIVATE_URL substring confusion |

## Deobfuscator Limitations

| Transform | Limitation |
|-----------|------------|
| NFKC normalization | Does NOT normalize Cyrillic homoglyphs that visually resemble Latin letters or digits (e.g., `Ӧ` (U+04E6) → `5`, `А` (U+0410) → `A`). NFKC only normalizes canonical equivalents. |
| Digit homoglyph map | No mapping exists for non-ASCII characters that visually resemble digits (e.g., Cyrillic letters that look like 0-9, superscript/subscript numerals). |
| Spoken number parser | Limited to single-digit words (`one`→`1`, ..., `nine`→`9`, `oh`→`0`). Does not handle multi-digit spoken numbers like `one hundred twenty three`. |
| Pig latin decoder | Heuristic-only; may produce incorrect reversals for words that happen to match the pattern but aren't pig latin. |
| Base64/hex decoders | Simple regex-based — may produce false positives on strings that happen to be valid base64 but aren't encoded PII. |

## Benchmark Limitations

| Issue | Details |
|-------|---------|
| Span mismatch for deobfuscated entities | The benchmark compares entity spans from the raw text against detected entities from the deobfuscated text. For any entity whose position shifts during deobfuscation (zero-width char removal, URL decoding, HTML entity decoding), the benchmark reports a false-negative even though the entity was correctly detected on the deobfuscated text. |
| Label coverage | Some examples have entities in the text that are not labeled in the entity list. This inflates false-positive counts for types like CITY, GPS, and COMPANY. |
| URL entity absence | The dataset contains 0 URL-typed entities, making URL metrics meaningless. |