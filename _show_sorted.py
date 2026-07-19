#!/usr/bin/env python3
import json
d = json.load(open('/tmp/recall-verify.json'))
r = d['detectors']['regex']
pt = r['per_type']
sorted_types = sorted(pt.items(), key=lambda x: x[1]['recall'])
print(f"{'Entity Type':25s} {'Precision':>9s} {'Recall':>7s} {'F1':>7s}  {'TP':>3s} {'FP':>3s} {'FN':>3s}")
print("-" * 70)
for et, m in sorted_types:
    print(f"{et:25s} {m['precision']:>9.4f} {m['recall']:>7.4f} {m['f1']:>7.4f}  {m['true_positives']:>3d} {m['false_positives']:>3d} {m['false_negatives']:>3d}")