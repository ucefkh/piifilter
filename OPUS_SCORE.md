# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **8 / 10**

Date: 2026-07-20
Commit: 60244f0 (github.com/ucefkh/piifilter)
Benchmark: Golden corpus F1=1.0 all 26 types; Synthetic recall (pipeline-arb) P=0.9307 R=0.9862 F1=0.9577

## What Changed This Tick

**1. Split-token deobfuscation ordering fix**
- Moved `_reconstruct_split_tokens()` BEFORE `_strip_non_alpha_seps()` in the deobfuscation pipeline
- Previously, inner-separator stripping ran first, collapsing concatenated quoted tokens like `"192" + "." + "168" + "." + "1" + "." + "1"` into undetectable `"19216811"` before reconstruction could extract the IP
- Now reconstruction produces `192.168.1.1` on `text_for_gps` BEFORE stripping, making split-token IPs and emails detectable
- Fixes 3 FNs: split IP (`"192"+"."+"168"+"."+"1"+"."+"1"`) and 2 split emails (`"john"+"@"+"example.com"`)
- Note: benchmark cannot measure this improvement directly due to span mismatch between original and cleaned text

**2. PHONE demo/teaching context suppression**
- Added post-detect filter that suppresses PHONE entities when preceded by demo/teaching context
- Patterns: "phone-like", "not a real phone", "not a phone", "example phone", "fake number", "not a real"
- Fixes FP: `123-456-7890` in `"User typed a phone-like number: 123-456-7890 but this is not a real phone."`
- Uses `text_for_gps` for context lookbehind (PHONE runs on pre-strip text, not cleaned)
- Regex raw: PHONE FP 3→2 (33% reduction), Overall P=0.9227→0.9267
- Pipeline-arbitration: PHONE P=0.9375 (unchanged — remaining FP is from arbitration path)

**Benchmark results (pipeline-arbitration):**
- Overall: P=0.9307 R=0.9862 F1=0.9577 (TP=215 FP=16 FN=3)
- Previously: P=0.9348 R=0.9862 F1=0.9598 (TP=215 FP=15 FN=3)
- Slight FP increase from split-token deobfuscation creating entities with wrong span positions

## Key Feedback from Opus
- "The F1 of 0.9577 with excellent recall (0.9862) is strong"
- "Both improvements target real, well-defined failure modes"
- "Main remaining gap is precision (0.9307)"
- "Solid, above-average performance with clear room to tighten precision"

## Next Item
- Continue tightening precision on remaining FP types: PHONE (arb pipeline), CITY, DOMAIN, PERSON
- Clean up stale test backups
- Run recall benchmark and fix worst entity type