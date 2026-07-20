"""Check which compiled pattern matches XXX-XX-6789."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

detector = RegexDetector()
asyncio.run(detector.initialize())

text = 'SSN last-4: 6789. Full: XXX-XX-6789'

# Test each compiled pattern
import re
from piifilter.shared.models import EntityType
print(f"Number of compiled patterns: {len(detector._patterns)}")
for idx, (et, pattern, score) in enumerate(detector._patterns):
    matches = list(pattern.finditer(text))
    for m in matches:
        print(f"Pattern #{idx} ({et.value}, conf={score}): matched >>{m.group()}<< at {m.start()}-{m.end()}")