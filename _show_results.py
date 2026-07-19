#!/usr/bin/env python3
import json
d = json.load(open('benchmarks/recall-results.json'))
r = d['detectors']['regex']
print(f'Total expected: {r["total_expected_entities"]}, Total detected: {r["total_detected_entities"]}')
print(f'Overall: TP={r["total_true_positives"]} FP={r["total_false_positives"]} FN={r["total_false_negatives"]}')
pt = r['per_type']
for et, metrics in sorted(pt.items()):
    print(f'  {et:25s} TP={metrics["true_positives"]:>2d} FP={metrics["false_positives"]:>2d} FN={metrics["false_negatives"]:>2d} P={metrics["precision"]:.4f} R={metrics["recall"]:.4f}')