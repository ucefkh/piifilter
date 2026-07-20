"""Check example 179 after the fix."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

text = 'SSN last-4: 6789. Full: XXX-XX-6789'
detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))
print(f'Detections ({len(detected)}):')
for d in detected:
    print(f'  {d.entity_type.value}: {d.text} (score={d.raw_score}) span={d.start}-{d.end}')

# Also check the context-keyword version
text2 = 'SSN: XXX-XX-6789'
detected2 = asyncio.run(detector.detect(text2))
print(f'\nWith SSN context:')
for d in detected2:
    print(f'  {d.entity_type.value}: {d.text} (score={d.raw_score})')

text3 = 'My SSN is XXX-XX-6789'
detected3 = asyncio.run(detector.detect(text3))
print(f'\nWith "My SSN is" context:')
for d in detected3:
    print(f'  {d.entity_type.value}: {d.text} (score={d.raw_score})')