"""Debug remaining missed phones with exact pattern testing."""
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'plugins/detector-presidio/src')

import json
import re

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)
examples = data['examples']

from piifilter_detector_regex.patterns import PATTERN_DEFS

phone_patterns = [(ptype, re.compile(pat), conf, pat) for ptype, pat, conf in PATTERN_DEFS if ptype == 'PHONE']

test_cases = [
    "07700 900 123",
    "49 30 12345678",
    "44 20 7946 0958", 
    "+1-555-123-4Ӧ97",
    "8613800138000",
]

for val in test_cases:
    print(f"\n=== Testing: \"{val}\" ===")
    # Check each pattern against the value directly
    for idx, (ptype, pat, conf, pat_str) in enumerate(phone_patterns):
        m = pat.search(val)
        if m:
            print(f"  [{idx}] MATCH: pat={pat_str[:80]} => match='{m.group()}' at [{m.start()}:{m.end()}]")
    # Check against a full sentence context
    for text_ctx in [f"Phone: {val}", f"Data: {val}", f"Hidden field: {val}"]:
        for idx, (ptype, pat, conf, pat_str) in enumerate(phone_patterns):
            m = pat.search(text_ctx)
            if m:
                print(f"  ctx='{text_ctx}' [{idx}] MATCH: '{m.group()}'")
                break