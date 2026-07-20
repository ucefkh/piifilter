#!/usr/bin/env python3
"""Inspect held-out results structure."""
import json

with open('benchmarks/heldout-results.json') as f:
    data = json.load(f)

print("Top-level keys:", list(data.keys()))
print()

# Try to find per-type breakdown
if 'per_type' in data:
    per_type = data['per_type']
elif 'per_category' in data:
    per_type = data['per_category']
elif 'entities' in data:
    per_type = data['entities']
else:
    # Search for nested structure
    for k, v in data.items():
        if isinstance(v, dict) and any(t in str(v.keys())[:200] for t in ['EMAIL', 'PERSON']):
            per_type = v
            print(f"Using key: {k}")
            break
    else:
        print("No per-type data found")
        print(json.dumps(data, indent=2)[:3000])
        exit()

for t, vals in sorted(per_type.items()):
    p = vals.get('precision', vals.get('P', 0))
    r = vals.get('recall', vals.get('R', 0))
    f1 = vals.get('f1', vals.get('F1', 0))
    tp = vals.get('true_positives', vals.get('TP', 0))
    fp = vals.get('false_positives', vals.get('FP', 0))
    fn = vals.get('false_negatives', vals.get('FN', 0))
    n = vals.get('n', vals.get('N', 0))
    fn_total = vals.get('false_negatives_total', vals.get('FN_total', 0))
    print(f'{t:25s} P={p:.4f} R={r:.4f} F1={f1:.4f} TP={tp} FP={fp} FN={fn} N={n}')