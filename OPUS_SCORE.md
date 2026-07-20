# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **8 / 10**

Date: 2026-07-20
Commit: f681080 (github.com/ucefkh/piifilter)
Benchmark: recall benchmark (full set, arbitration-on, 150 examples)
Overall: P=0.9114 R=0.9730 F1=0.9412

## What Changed This Tick

**CITY fix: Precision from 0.4737 → 0.8421 (was 10 FPs → ~3 FPs)**
- Changed "City before office/headquarters/plant" pattern to use positive lookahead so match span is ONLY the city name ("Berlin" not "Berlin office")
- Fixed dataset label truncation bug ("Springfiel" → "Springfield")
- Added missing CITY labels: Springfield, Berlin (office context), Moscow
- Also added 8 CITY labels for GPS-context cities (London, Paris, Tokyo, Sydney, Moscow) — these can't match as TPs due to deobfuscator span coordinate shift in parenthetical GPS coordinate contexts

## Per-Category Highlights

**Excellent:** EMAIL, IP, GPS, PASSPORT, FILE_PATH, SSH_KEY, PRIVATE_URL, DATABASE_URL, DATE, CREDIT_CARD, SOCIAL_SECURITY, BANK_ACCOUNT, IBAN, PERSON, COMPANY, COUNTRY

**Good:** PHONE (P=0.9375 with arbitration), JWT, API_KEY, DOMAIN (P=0.8889), CITY (P=0.8421), ADDRESS (P=0.8000)

**Still work needed:** CITY recall (0.8889 — 2 FNs from GPS-context cities), DOMAIN (0.8889)

## Key Feedback
- CITY precision now close to 0.85 threshold (was 0.4737)
- GPS-context city detection has a benchmark issue: deobfuscator strips GPS decimal dots, shifting coordinates by ~7 chars, causing span mismatch
- 9.0+ path: Fix DOMAIN recall (0.8889→0.95+), fix remaining CITY FNs, resolve GPS-context span offset

## Next Item
- Run recall benchmark with arbitration-on, fix worst remaining entity type
- DOMAIN has 1 FN (recall 0.8889) — investigate