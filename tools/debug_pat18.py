"""Check which pattern #18 is."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector
import re

detector = RegexDetector()
asyncio.run(detector.initialize())

text = 'SSN last-4: 6789. Full: XXX-XX-6789'

# Pattern #18
et, pat, score = detector._patterns[18]
print(f"Pattern 18: {et.value}, conf={score}")
print(f"Regex: {pat.pattern[:200]}")
match = pat.search(text)
if match:
    print(f"Match: {match.group()} at {match.start()}-{match.end()}")

# Also check patterns around it
for idx in range(16, 22):
    et, pat, score = detector._patterns[idx]
    m = pat.search(text)
    if m:
        print(f"\nPattern {idx} ({et.value}, conf={score}): matched >>{m.group()}<<")
        print(f"  regex: {pat.pattern[:200]}")