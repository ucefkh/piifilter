"""Debug MASKED_SSN detection on example 179."""
import re
text = 'SSN last-4: 6789. Full: XXX-XX-6789'

patterns = [
    ("Line 73", r'(?i)\b(?:ssn|social security|ss#)\s+\d[X*#]{2}[- ][X*#]{2}[- ]\d{4}\b'),
    ("Line 74", r'(?i)\b(?:ssn|social security|ss#)\s+[X*#]{3}[- ]{2,4}\d{4}\b'),
    ("Line 75", r'(?i)\b(?:ssn|social security|ss#)\s+[X*#]{3}[- ]\d{4}\b'),
    ("Line 77", r'(?i)(?:mask|redact|obfuscat)[a-z]*\s*(?:social|ssn|ss#)\s*:?\s*[X*#]{3}[- ]\d{2}[- ]\d{4}\b'),
    ("Line 79", r'(?i)\b(?:encoded|hidden\s+field|encrypted|obfuscat)[a-z]*\s*[:=]\s*[A-Za-z0-9+/=]{9,}\b'),
    ("Line 81", r'\b\d{3}[\u00A0 ]\d{2}[\u00A0 ]\d{4}\s+\(segmented\)\b'),
    ("Line 89", r'(?<!\d)\d{3,4}[-\u00A0 ]\d{2}[-\u00A0 ]?\d{3,4}(?!\d)'),
    ("Line 93", r'\b\d{4}[-\u00A0 ]\d{2}[-\u00A0 ]?\d{3,4}\b'),
    ("Line 99", r'\b(?!000|666)\d{3}(?!000|666)\d{6}\b'),
]

for name, pat in patterns:
    matches = re.findall(pat, text)
    if matches:
        print(f'{name}: {matches}')
    else:
        print(f'{name}: (no match)')

# Also check the actual detector.py for any inline patterns
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))
print(f'\nFull detection results ({len(detected)}):')
for d in detected:
    print(f'  {d.entity_type.value}: {repr(d.value)} score={d.confidence} span={d.start}-{d.end}')