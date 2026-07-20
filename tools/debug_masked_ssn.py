#!/usr/bin/env uv run python
"""Debug MASKED_SSN detection on example 179."""
import json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
import re
from piifilter_detector_regex.detector import RegexDetector

text = 'SSN last-4: 6789. Full: XXX-XX-6789'

# Check each pattern
import importlib
import piifilter_detector_regex.patterns as pat_mod
patterns = pat_mod.SOCIAL_SECURITY_PATTERNS + pat_mod.MASKED_PATTERNS

print("=== Checking all patterns against text ===")
for et, pattern, conf in patterns:
    # Only check MASKED_SSN patterns
    if 'MASKED' in et or 'MASKED' in pat_mod.getattr(pat_mod, et, str):
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for m in matches:
            print(f"  Pattern ({et}, conf={conf}):")
            print(f"    Matched: {repr(m.group())}")
            print(f"    At: {m.start()}-{m.end()}")
            print(f"    Pattern: {pattern[:80]}...")

print("\n=== Checking MASKED_PATTERNS ===")
for et, pattern, conf in pat_mod.MASKED_PATTERNS:
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    for m in matches:
        print(f"  Pattern ({et}, conf={conf}):")
        print(f"    Matched: {repr(m.group())}")
        print(f"    At: {m.start()}-{m.end()}")
        print(f"    Pattern: {pattern[:100]}...")

# Full detection
detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))
print(f"\n=== All detections ({len(detected)}) ===")
for d in detected:
    print(f"  Type: {d.entity_type.value}, Value: {repr(d.value)}, Score: {d.confidence}, Span: {d.start}-{d.end}")