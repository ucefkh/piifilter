#!/usr/bin/env python3
"""Analyze remaining failures."""
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
            results.append({'type': type_name, 'value': m.group(), 'start': s, 'end': e, 'score': score, 'pattern_type': type_name})
            seen.append((s, e))
    results.sort(key=lambda x: x['start'])
    return results

# Check all remaining false negatives for regex
print("=== REMAINING FALSE NEGATIVES (regex) ===")
fn_by_type = {t: [] for t in set(e['type'] for ex in examples for e in ex['entities'])}
for i, ex in enumerate(examples):
    detected = detect(ex['text'])
    for ent in ex['entities']:
        found = any(
            d['start'] <= ent['start'] and d['end'] >= ent['end'] and d['type'] == ent['type']
            for d in detected
        )
        if not found:
            fn_by_type.setdefault(ent['type'], []).append((i, ent, ex['text']))

for t in sorted(fn_by_type.keys()):
    if fn_by_type[t]:
        print(f"\n  {t}: {len(fn_by_type[t])} missed")
        for i, ent, text in fn_by_type[t]:
            ctx_start = max(0, ent['start']-20)
            ctx_end = min(len(text), ent['end']+20)
            print(f"    Ex {i}: expected={repr(ent)}, context={repr(text[ctx_start:ctx_end])}")

print("\n\n=== REMAINING FALSE POSITIVES (regex) ===")
for i, ex in enumerate(examples):
    detected = detect(ex['text'])
    for d in detected:
        expected = [e for e in ex['entities'] if e['type'] == d['type'] and 
                   max(e['start'], d['start']) < min(e['end'], d['end'])]
        if not expected:
            # Check if it overlaps any expected entity of different type
            expected_other = [e for e in ex['entities'] if e['type'] != d['type'] and 
                            max(e['start'], d['start']) < min(e['end'], d['end'])]
            overlap_label = ""
            if expected_other:
                overlap_label = f" (overlaps expected {expected_other[0]['type']}: {repr(expected_other[0]['value'])})"
            print(f"  Ex {i} FP: {d['type']}={repr(d['value'][:50])} score={d['score']}{overlap_label}")