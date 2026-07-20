# PIIFilter FINAL — Opus 4.8 Score

## Latest Score: **7 / 10**

Date: 2026-07-20
Commit: 3c41808 (github.com/ucefkh/piifilter)
Benchmark: Golden corpus F1=1.0 all 26 types; Synthetic recall (pipeline-arb) P=0.9307 R=0.9862 F1=0.9577

## What Changed This Tick

**1. Fixed _CONCAT_RE to handle single-quoted split tokens**
- Previously `_CONCAT_RE` regex only matched double-quoted strings (`"john" + "@" + "example.com"`)
- Now also matches single-quoted strings (`'john' + '@' + 'example.com'`)
- The `_rebuild_concat` extraction function similarly updated to handle both quote types
- Fixes real-world email obfuscation `// email = 'john' + '@' + 'example.com'` that was previously missed
- Manual verification: deobfuscator correctly reconstructs `john@example.com`, detector finds it

**Note:** This fix cannot be directly measured by the synthetic recall benchmark because the dataset annotation uses original-text coordinates while the detector returns deobfuscated-text coordinates (span mismatch). The golden corpus benchmark already had F1=1.0 across all 26 types.

## Key Feedback from Opus
- "Improved realism incrementally"
- Score: 7/10 for addressing a real-world gap that won't show in synthetic metrics

## Next Item
- Continue tightening precision on remaining FP types: EMAIL, PERSON, PHONE, IP_ADDRESS
- Run recall benchmark and fix worst entity type (recall <0.95 or precision <0.85)
- Clean up stale test backups