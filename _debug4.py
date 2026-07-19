"""Check what catches 8613800138000."""
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'plugins/detector-presidio/src')

import json, re

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)
examples = data['examples']

from piifilter_detector_regex.patterns import PATTERN_DEFS

patterns = [(ptype, re.compile(pat), conf, pat) for ptype, pat, conf in PATTERN_DEFS]

val = "8613800138000"
texts_ctx = [
    val,
    f"Encoded: {val}",
    f"Data: {val}",
]

for text in texts_ctx:
    print(f"\n=== Context: '{text}' ===")
    for idx, (ptype, pat, conf, pat_str) in enumerate(patterns):
        m = pat.search(text)
        if m:
            print(f"  [{idx}] {ptype} (conf={conf}): match='{m.group()}'")