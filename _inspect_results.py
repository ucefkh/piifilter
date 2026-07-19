#!/usr/bin/env python3
"""Inspect recall results JSON."""
import json

data = json.load(open('benchmarks/recall-results.json'))
print("Top-level keys:", list(data.keys()))

# Find regex results
regex_key = None
for k, v in data.items():
    if isinstance(v, dict) and 'true_positives' in v or 'overall_f1' in v:
        print(f"\n{k}:")
        if 'entity_results' in v:
            for et, res in v['entity_results'].items():
                print(f"  {et}: {json.dumps(res, indent=4)[:200]}")
        else:
            print(f"  {json.dumps(v, indent=4)[:500]}")
    elif isinstance(v, dict):
        for k2, v2 in v.items():
            if isinstance(v2, dict) and 'overall_f1' in v2:
                print(f"\n{k} -> {k2}:")
                if 'entity_results' in v2:
                    for et, res in v2['entity_results'].items():
                        if 'GPS' in str(et).upper():
                            print(f"  {et}: {json.dumps(res, indent=4)[:300]}")
                print(f"  overall: precision={v2.get('overall_precision')}, recall={v2.get('overall_recall')}, f1={v2.get('overall_f1')}")