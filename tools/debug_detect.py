"""Debug detection on example 179 text."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

text = 'SSN last-4: 6789. Full: XXX-XX-6789'
detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))
print(f'Total detections: {len(detected)}')
for d in detected:
    print(f'  Type: {d.entity_type.value}')
    print(f'  Text: {repr(d.text)}')
    print(f'  Raw Score: {d.raw_score}')
    print(f'  Span: {d.start}-{d.end}')
    print()