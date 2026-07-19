#!/usr/bin/env python3
import re
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
ssn_patterns = [(i, p, s) for i,(t,p,s) in enumerate(PATTERN_DEFS) if t == 'SOCIAL_SECURITY']
for idx, pat, score in ssn_patterns:
    compiled = re.compile(pat, re.UNICODE)
    print(f'Pattern #{idx}: score={score}')
    print(f'  {pat}')
print(f'\nTotal SOCIAL_SECURITY patterns: {len(ssn_patterns)}')