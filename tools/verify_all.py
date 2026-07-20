"""Verify all cases after the fix."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

detector = RegexDetector()
asyncio.run(detector.initialize())

cases = [
    'SSN last-4: 6789. Full: XXX-XX-6789',
    'SSN: XXX-XX-6789',
    'My SSN is XXX-XX-6789',
    'SS# XXX-XX-6789',
    'social security: XXX-XX-6789',
    'Tax ID: XXX-XX-6789',
    'Full: XXX-XX-6789',
    'See also: XXX-XX-6789',
    'XXX-XX-6789',
]

for text in cases:
    detected = asyncio.run(detector.detect(text))
    print(f'{repr(text):50s} -> {[(d.entity_type.value, d.raw_score) for d in detected]}')