#!/usr/bin/env uv run python
"""Find which example triggers MASKED_SSN FP and what the actual golden corpus says about MASKED_SSN."""
import json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

corpus = json.load(open('benchmarks/data/golden_corpus.json'))
examples = corpus['examples']

# Check golden
masked_ssn_golden = [e for ex in examples for e in ex.get('entities', []) if e['type'] == 'MASKED_SSN']
print(f"MASKED_SSN in golden: {len(masked_ssn_golden)}")
for e in masked_ssn_golden:
    print(f"  {e}")

# Run detection and find any MASKED_SSN
detector = RegexDetector()
asyncio.run(detector.initialize())

for i, ex in enumerate(examples):
    text = ex["text"]
    detected = asyncio.run(detector.detect(text))
    for d in detected:
        if hasattr(d, 'entity_type'):
            et = d.entity_type.value
        else:
            et = d.get('type', d.get('entity_type', '?'))
        if et == 'MASKED_SSN':
            val = d.value if hasattr(d, 'value') else ''
            print(f"\nExample {i} triggers MASKED_SSN:")
            print(f"  Value: {repr(val)}")
            print(f"  Text: {repr(text)}")