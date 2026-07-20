"""Debug - what the detector actually loads."""
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

# Force reload everything
import piifilter_detector_regex.patterns
from piifilter_detector_regex.patterns import PATTERN_DEFS
import importlib
importlib.reload(piifilter_detector_regex.patterns)

# Get fresh
from piifilter_detector_regex.patterns import PATTERN_DEFS
import re

# Find pattern 4
city_with_in = [p for p in PATTERN_DEFS if p[0] == 'CITY' and 'in ' in p[1] and 'Settings' in p[1]]
print(f'Found {len(city_with_in)} patterns with "in " and Settings in denylist')
for name, raw, conf in city_with_in:
    pat = re.compile(raw, re.UNICODE)
    for test in ['in Settings', 'in Boston', 'in System', 'in Config']:
        m = pat.search(test)
        status = 'MATCH' if m else 'BLOCKED'
        print(f'  {status}: "{test}"')
    print()

# Now test the detector
import asyncio
from piifilter_detector_regex.detector import RegexDetector

async def test():
    d = RegexDetector()
    await d.initialize()
    for text in ['in Settings', 'in System', 'in Config', 'in Mode', 'in Boston', 'I live in Miami', 'in Paris']:
        results = await d.detect(text)
        city_results = [r for r in results if r.entity_type.value == 'CITY']
        if city_results:
            for r in city_results:
                print(f'DETECTOR: "{text}" -> CITY: "{r.text}" score={r.raw_score}')
        else:
            print(f'DETECTOR: "{text}" -> none')

asyncio.run(test())