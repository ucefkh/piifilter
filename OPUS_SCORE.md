# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **6 / 10**

Date: 2026-07-20
Commit: 6e538a3 (github.com/ucefkh/piifilter)
Benchmark: Golden corpus F1=1.0 all 26 types; Synthetic recall (pipeline-arb) P=0.9307 R=0.9862 F1=0.9577

## What Changed This Tick

**PHONE/CC/IP precision improvement via structural overlap filtering**
- Extended `_filter_phone_overlap()` to check low-confidence PHONE matches against CREDIT_CARD, SOCIAL_SECURITY, IBAN, BANK_ACCOUNT, API_KEY, and DATABASE_URL entities by digit-content overlap
- Before (pipeline-arbitration):
  - PHONE: P=0.8333 (3 FPs)
  - CREDIT_CARD: P=0.5833 (5 FPs)
  - IP_ADDRESS: P=0.8750 (2 FPs)
- After (pipeline-arbitration):
  - PHONE: P=0.9375 (1 FP) 
  - CREDIT_CARD: P=1.0000 (0 FPs)
  - IP_ADDRESS: P=1.0000 (0 FPs)
- Golden corpus (balanced mode): All 26 entity types at 100% F1

## Per-Category Highlights (pipeline-arbitration)

**Perfect (P=1.0, R=1.0):** API_KEY, BANK_ACCOUNT, COMPANY, COUNTRY, CREDIT_CARD, CUSTOMER_NAME, DATABASE_URL, GPS, IBAN, JWT, PASSPORT, PROJECT_NAME, SSH_KEY

**Excellent (P>0.85, R>0.95):** 
- PHONE: P=0.9375 R=1.0
- CITY: P=0.9333 R=1.0
- EMAIL: P=0.9302 R=0.9524
- DOMAIN: P=0.9000 R=1.0
- PERSON: P=0.9000 R=1.0
- FILE_PATH, PRIVATE_URL, SOCIAL_SECURITY, EMPLOYEE_NAME: P=0.8571-0.8750 R=1.0

**Below threshold:** 
- ADDRESS: P=0.8000 (1 FP, N=4)
- IP_ADDRESS: R=0.9333 (1 FN, N=15)

## Key Feedback from Opus
- The dedup improvement is legitimate and well-targeted
- Synthetic F1=0.96 is strong but improvement ceiling limits score
- Regret: golden corpus 100% metrics viewed skeptically despite being regression-tested

## Next Item
- Fix ADDRESS FP (investigate lone P=0.8000 on recall benchmark)
- Fix IP_ADDRESS FN (1 FN on space-separated or non-standard format)