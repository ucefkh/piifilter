"""Check which pattern matches after the fix."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

detector = RegexDetector()
asyncio.run(detector.initialize())

text = 'SSN last-4: 6789. Full: XXX-XX-6789'

for idx, (et, pat, score) in enumerate(detector._patterns):
    match = pat.search(text)
    if match:
        print(f"Pattern #{idx} ({et.value}, {score}): >>{match.group()}<< at {match.start()}-{match.end()}")

# Check full detection
detected = asyncio.run(detector.detect(text))
print(f"\nFull detection ({len(detected)}):")
for d in detected:
    print(f"  {d.entity_type.value}: {d.text} ({d.raw_score})")