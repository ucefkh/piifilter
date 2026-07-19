#!/usr/bin/env python3
import json
d = json.load(open('/tmp/recall-verify.json'))
examples = d['detectors']['regex']['example_results']

# Find examples with SOCIAL_SECURITY false negatives
print("=== SOCIAL_SECURITY FNs ===")
for ex in examples:
    if 'SOCIAL_SECURITY' in ex['expected_types'] and ex.get('false_negatives', 0) > 0:
        print(f"  #{ex['index']}: FN={ex['false_negatives']} text={ex['text_preview']}")

print("\n=== ADDRESS FNs ===")
for ex in examples:
    if 'ADDRESS' in ex['expected_types'] and ex.get('false_negatives', 0) > 0:
        print(f"  #{ex['index']}: FN={ex['false_negatives']} text={ex['text_preview']}")

print("\n=== EMAIL FNs ===")
for ex in examples:
    if 'EMAIL' in ex['expected_types'] and ex.get('false_negatives', 0) > 0:
        fn = ex.get('false_negatives', 0) 
        if fn > 0:
            print(f"  #{ex['index']}: FN={fn} text={ex['text_preview']}")