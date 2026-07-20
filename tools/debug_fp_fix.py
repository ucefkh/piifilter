"""Before fix: check benchmark with current pattern."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

# Check the FP text
text = 'SSN last-4: 6789. Full: XXX-XX-6789'
detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))
print(f'FP test: {len(detected)} detection(s) on "Full: XXX-XX-6789"')
for d in detected:
    print(f'  {d.entity_type.value}: {d.text} (score={d.raw_score})')

# Check legitimate case still works
text2 = 'SSN: XXX-XX-6789'
detected2 = asyncio.run(detector.detect(text2))
print(f'\nLegit test: {len(detected2)} detection(s) on "SSN: XXX-XX-6789"')
for d in detected2:
    print(f'  {d.entity_type.value}: {d.text} (score={d.raw_score})')

# Check another legit case
text3 = 'My SSN is XXX-XX-6789'
detected3 = asyncio.run(detector.detect(text3))
print(f'\nLegit test2: {len(detected3)} detection(s) on "My SSN is XXX-XX-6789"')
for d in detected3:
    print(f'  {d.entity_type.value}: {d.text} (score={d.raw_score})')

# Check what the bare pattern does in isolation
import re
bare_pattern = re.compile(r'[X*#]{3}[- ][X*#]{2}[- ]\d{4}')
print(f'\nBare pattern on "Full: XXX-XX-6789": {[m.group() for m in bare_pattern.finditer(text)]}')
print(f'Bare pattern on "SSN: XXX-XX-6789": {[m.group() for m in bare_pattern.finditer(text2)]}')