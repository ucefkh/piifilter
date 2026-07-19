#!/usr/bin/env python3
"""Analyze which IPs, Countries, and PRIVATE_URLs are failing."""
import json
import re

# Load the current patterns
import sys
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter_detector_regex.patterns import PATTERN_DEFS

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

# For each entity type, compile patterns and test
patterns_by_type = {}
for type_name, raw_pattern, score in PATTERN_DEFS:
    patterns_by_type.setdefault(type_name, []).append((re.compile(raw_pattern, re.IGNORECASE), score))

def detect(text):
    results = []
    seen = []
    for type_name, compiled_patterns in patterns_by_type.items():
        for pattern, score in compiled_patterns:
            for m in pattern.finditer(text):
                s, e = m.start(), m.end()
                if s == e: continue
                if any(st <= s and e <= en for st, en in seen): continue
                results.append({'type': type_name, 'value': m.group(), 'start': s, 'end': e, 'score': score})
                seen.append((s, e))
    results.sort(key=lambda x: x['start'])
    return results

# Test each IP example
print('=== IP_ADDRESS examples + what regex detects ===')
for i, ex in enumerate(examples):
    for ent in ex['entities']:
        if ent['type'] == 'IP_ADDRESS':
            detected = detect(ex['text'])
            # Find what was detected at that position
            ip_detections = [d for d in detected if d['type'] in ('IP_ADDRESS', 'PRIVATE_URL') and 
                           d['start'] <= ent['start'] and d['end'] >= ent['end']]
            ip_missed = not any(d['start'] <= ent['start'] and d['end'] >= ent['end'] for d in detected)
            print(f'  Ex {i}: expected IP={repr(ent)}', end='')
            if ip_detections:
                print(f'  -> DETECTED AS: {[(d["type"], d["value"]) for d in ip_detections]}')
            elif ip_missed:
                # What was detected in the area?
                nearby = [d for d in detected if abs(d['start'] - ent['start']) < 10 or abs(d['end'] - ent['end']) < 10]
                print(f'  -> MISSED! Nearby detections: {[(d["type"], d["value"]) for d in nearby]}')
                print(f'  -> Text: {repr(ex["text"])}')

print()
print('=== COUNTRY examples + what regex detects ===')
for i, ex in enumerate(examples):
    for ent in ex['entities']:
        if ent['type'] == 'COUNTRY':
            detected = detect(ex['text'])
            country_detections = [d for d in detected if d['type'] in ('COUNTRY', 'CITY') and 
                                d['start'] <= ent['start'] and d['end'] >= ent['end']]
            missed = not any(d['start'] <= ent['start'] and d['end'] >= ent['end'] for d in detected)
            print(f'  Ex {i}: expected COUNTRY={repr(ent)}', end='')
            if country_detections:
                print(f'  -> DETECTED AS: {[(d["type"], d["value"]) for d in country_detections]}')
            elif missed:
                print(f'  -> MISSED!')
                print(f'  -> All detections: {[(d["type"], d["value"], d["start"], d["end"]) for d in detected]}')

print()
print('=== PRIVATE_URL false positives ===')
for i, ex in enumerate(examples):
    detected = detect(ex['text'])
    private_detections = [d for d in detected if d['type'] == 'PRIVATE_URL']
    # Check which private URL detections overlap with non-PRIVATE_URL labels
    expected_entities = list(ex['entities'])
    for d in private_detections:
        # Is this a false positive (detected as PRIVATE_URL but labeled as something else)?
        expected_at_span = [e for e in ex['entities'] if e['type'] != 'PRIVATE_URL' and 
                          max(e['start'], d['start']) < min(e['end'], d['end'])]
        if expected_at_span or not any(e['start'] <= d['start'] and d['end'] <= e['end'] for e in ex['entities'] if e.get('type')):
            true_fp = not any(e['type'] == 'PRIVATE_URL' and e['start'] <= d['start'] and d['end'] <= e['end'] for e in ex['entities'])
            if true_fp:
                print(f'  Ex {i}: FP PRIVATE_URL={repr(d["value"][:60])} text={repr(ex["text"][:80])}')
                if expected_at_span:
                    print(f'     Expected: {expected_at_span}')