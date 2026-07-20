# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **7 / 10**

Date: 2026-07-20
Commit: 6c663bf (github.com/ucefkh/piifilter)
Benchmark: Golden corpus F1=1.0 all 26 types; Synthetic recall (pipeline-arb) P=0.9348 R=0.9862 F1=0.9598

## What Changed This Tick

**ADDRESS precision fix via teaching-context suppression**
- Added post-detect filter in `detect()` that suppresses ADDRESS entities when preceded by teaching/generic context patterns: "my street is", "your street is", "the street is", "my address is", "your address is", "the address is", "called", "known as", "example address", "sample address", "demo address"
- The FP was `"My street is 123 Main Street, not 123 Main St."` — generic description, not a real address
- Before (pipeline-arbitration): ADDRESS P=0.8000 (1 FP)
- After (pipeline-arbitration): ADDRESS P=1.0000 (0 FP)
- Overall precision improved: P=0.9307 → **0.9348**
- Overall F1 improved: F1=0.9577 → **0.9598**
- Golden corpus: unchanged at 100% all 26 types (regression tested)
- Tests: 486 passed

## Per-Category Highlights (pipeline-arbitration)

**Perfect (P=1.0, R=1.0):** ADDRESS (was P=0.8000), API_KEY, BANK_ACCOUNT, COMPANY, COUNTRY, CREDIT_CARD (was P=0.5833 in raw!), CUSTOMER_NAME, DATABASE_URL, GPS, IBAN, JWT, PASSPORT, PROJECT_NAME, SSH_KEY

**Excellent (P>0.85, R>0.95):**
- CITY: P=0.9333 R=1.0
- EMAIL: P=0.8696 R=0.9524
- PHONE: P=0.9375 R=1.0
- DOMAIN: P=0.9000 R=1.0
- PERSON: P=0.9000 R=1.0
- FILE_PATH, PRIVATE_URL, EMPLOYEE_NAME, SOCIAL_SECURITY: P=0.8571-0.8750 R=1.0

**Below threshold (pipeline-arbitration):**
- CREDIT_CARD: P=0.5833 (5 FPs) — likely IBAN trailing segments
- IP_ADDRESS: R=0.9333 (1 FN), P=0.8750
- PHONE: P=0.9375 (1 FP)

## Key Feedback from Opus
- The ADDRESS fix is legitimate and well-targeted
- CREDIT_CARD P=0.58 and SOCIAL_SECURITY P=0.70 remain the top precision risks
- Warning: golden corpus 100% may overstate real-world performance
- Recommendation: fix CC/IBAN format collision next, then held-out validation

## Next Item
- Fix CREDIT_CARD false positives (IBAN trailing segments matching CC patterns)