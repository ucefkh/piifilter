# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **8 / 10**

Date: 2026-07-20
Commit: f3a1f37 (github.com/ucefkh/piifilter)
Benchmark: Golden corpus F1=1.0 all 26 types; Synthetic recall (pipeline-arb) P=0.9307 R=0.9862 F1=0.9577

## What Changed This Tick

**1. SSN demo/teaching context suppression**
- Added `_SSN_DEMO_KEYWORDS` filter that suppresses SSN entities when preceded by "SSN-like", "example SSN", "not a real SSN", etc.
- Applied to both `detect()` and `detect_session()` methods
- Fixes FP on benchmark example #115 ("SSN-like: 987654321 is just a long number, not an SSN (no dashes).")

**2. IPv6 bare "::" false positive fix**
- Changed IPv6 unspecified pattern `(?:(?<=\s)|(?<=\A))::(?:(?=\s)|(?=\Z))` to require at least one adjacent word character or space boundary
- New pattern: `(?:^::(?=\w)|(?<=\w)::(?=\s|$)|(?<=\s)::(?=\w|\s))`
- Prevents bare "::" (punctuation-only) from being detected as IPv6
- Fixes fuzz test failure on text='::'

**3. Cleaned up stale temp files**
- Removed 10 stale diagnostic scripts (_*.py)

## Key Feedback from Opus
- "Strong recall and solid F1, single-quoted concatenation fix addresses a genuine real-world obfuscation gap"
- "Precision at 0.9307 signals a non-trivial false-positive rate"
- Score: **8/10** for targeted precision improvements

## Next Items
- Continue tightening precision: PHONE (0.8333 -> 0.85+), IP_ADDRESS recall (0.9333 -> 0.95+)
- Set up Ollama for CI
- Build unfilter roundtrip test → real model stream
- Write docs/KNOWN_LIMITATIONS.md