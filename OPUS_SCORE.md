# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **8 / 10**

Date: 2026-07-20
Commit: 98001c8 (github.com/ucefkh/piifilter)

## What Changed This Tick

**1. Fixed PHONE bare-digit false positives in _filter_phone_overlap**

Fixed a critical bug in `_filter_phone_overlap` that was causing 2 extra PHONE FPs. The filter was:
- **Wrongly preserving** bare-digit stripped duplicates (e.g. `4155552671`) when they matched a pre-strip phone's digit content — these stripped versions have incorrect span positions on the deobfuscated text and overlap with correctly-formatted pre-strip phones
- **Wrongly self-suppressing** pre-strip phone entities (e.g. `555-123-4567` at 0.70 confidence) because their own digit content matched themselves in the pre-strip digit lookup table

**Fix:** Pre-strip phone entities are now always preserved by exact value match. Only bare-digit stripped duplicates (no separator characters like `-`, `.`, `(`, `)`, spaces) are suppressed when a pre-strip phone with matching digit content exists.

**Results (arbitration-on):**
- **PHONE**: TP=15, FP=1, recall=1.0, precision=**0.9375** (was 0.8333, 3 FPs → 1 FP)
- Additional improvements from arbitration:
  - **IP_ADDRESS**: precision=0.9333 (was 0.8750 in raw)
  - **SOCIAL_SECURITY**: precision=1.0 (was 0.7778 in raw)  
  - **PERSON**: precision=0.9000 (was 0.8182 in raw)

## Key Feedback from Opus
- Score: **8/10** for targeted precision improvement on PHONE

## Next Items
- Fix remaining PHONE FP (URL-encoded %2B → ` +1-555-123-4567` span mismatch)
- Fix IP_ADDRESS recall (0.9333 → 0.95+) 
- Set up Ollama for CI
- Write docs/KNOWN_LIMITATIONS.md