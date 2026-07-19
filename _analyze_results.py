#!/usr/bin/env python3
import json
data = json.load(open('benchmarks/recall-results.json'))
pt = data['detectors']['regex']['per_type']
sorted_types = sorted(pt.items(), key=lambda x: x[1]['recall'])
print("Regex detector — sorted by recall ascending:")
print(f"{'Entity Type':25s} {'Precision':>9s} {'Recall':>7s} {'F1':>7s}  {'TP':>3s} {'FP':>3s} {'FN':>3s}")
print("-" * 65)
for et, m in sorted_types:
    print(f"{et:25s} {m['precision']:>9.4f} {m['recall']:>7.4f} {m['f1']:>7.4f}  {m['true_positives']:>3d} {m['false_positives']:>3d} {m['false_negatives']:>3d}")