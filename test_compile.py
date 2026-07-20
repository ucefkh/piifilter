#!/usr/bin/env python3
"""Test that all CITY patterns compile correctly."""
import re
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

city_patterns = [(i, pat, conf) for i, (etype, pat, conf) in enumerate(PATTERN_DEFS) if etype == 'CITY']
print(f'Total CITY patterns: {len(city_patterns)}')
errors = 0
for i, pat, conf in city_patterns:
    try:
        re.compile(pat)
        print(f'  [{i}] conf={conf:.2f} OK')
    except re.error as e:
        print(f'  [{i}] conf={conf:.2f} ERROR: {e}')
        errors += 1

if errors:
    print(f'\n{errors} ERRORS FOUND')
    sys.exit(1)
else:
    print(f'\nAll patterns compile successfully')