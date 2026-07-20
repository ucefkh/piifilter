# PIIFilter FINAL — Opus 4.8 Score

## Final Score: **8.7 / 10**

Date: 2026-07-20
Commit: 6a50f7f (github.com/ucefkh/piifilter)
Benchmark: pipeline-arbitration, held-out 20%, 2365 examples, 473 test set
Overall: P=0.878 R=0.920 F1=0.899

## Per-Category Highlights

**Excellent:** EMAIL (0.991), IP (0.989), GPS (1.0), PASSPORT (1.0), FILE_PATH (1.0),
SSH_KEY (1.0), PRIVATE_URL (1.0), DATABASE_URL (1.0), DATE (1.0),
CREDIT_CARD (0.976), SOCIAL_SECURITY (0.974)

**Good:** PHONE (0.944), JWT (0.933), API_KEY (0.952), PERSON (0.881),
BANK_ACCOUNT (0.933), ADDRESS (0.919), IBAN (0.923)

**Weak/broken:** CITY (F1=0.267), DOMAIN (P=0.469), COUNTRY (F1=0.600),
URL (R=0.656), COMPANY (R=0.773)

## Key Feedback

- Not 9.5 — two broken categories (CITY, DOMAIN) cap the score
- DOMAIN precision (P=0.469, 17 FP) is the #1 problem — 25% of all FPs
- 9.5 path: Fix DOMAIN P→0.85+, fix CITY R, grow low-N category evidence
- Pip installable as beta with honest caveats about geographic-entity gaps