#!/usr/bin/env python3
"""Analyze remaining failures more precisely."""
import json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
import re

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

# Build compiled patterns
patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    patterns.append((type_name, re.compile(raw_pattern, re.IGNORECASE), score))

def detect(text):
    results = []
    seen = []
    for type_name, pattern, score in patterns:
        for m in pattern.finditer(text):
            s, e = m.start(), m.end()
            if s == e: continue
            if any(st <= s and e <= en for st, en in seen): continue
            results.append({'type': type_name, 'value': m.group(), 'start': s, 'end': e, 'score': score})
            seen.append((s, e))
    results.sort(key=lambda x: x['start'])
    return results

print("=== ALL FALSE NEGATIVES ===")
for i, ex in enumerate(examples):
    detected = detect(ex['text'])
    for ent in ex['entities']:
        found = any(d['start'] <= ent['start'] and d['end'] >= ent['end'] and d['type'] == ent['type'] for d in detected)
        if not found:
            # Check what else was detected at/near this span
            overlap = [d for d in detected if max(d['start'], ent['start']) < min(d['end'], ent['end'])]
            print(f"  FN Ex {i}: expected {ent['type']}={repr(ent['value'])} at [{ent['start']}:{ent['end']}]")
            if overlap:
                print(f"         Overlapping detections: {[(o['type'], repr(o['value']), o['start'], o['end']) for o in overlap]}")
            else:
                print(f"         No detection at this span")
                print(f"         All detections: {[(d['type'], repr(d['value']), d['start'], d['end']) for d in detected[:5]]}")

print("\n\n=== FALSE POSITIVES that overlap expected entities ===")
for i, ex in enumerate(examples):
    detected = detect(ex['text'])
    for d in detected:
        expected_at_span = [e for e in ex['entities'] if e['type'] != d['type'] and 
                           max(e['start'], d['start']) < min(e['end'], d['end'])]
        if expected_at_span:
            print(f"  FP Ex {i}: {d['type']}={repr(d['value'][:60])} score={d['score']}")
            print(f"         Overlaps expected: {[(e['type'], repr(e['value'])) for e in expected_at_span]}")