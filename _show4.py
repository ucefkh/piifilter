import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
for et, m in sorted(r['per_type'].items()):
    print(f"{et:<20} precision={m['precision']:.4f} recall={m['recall']:.4f} TP={m['true_positives']:<4} FP={m['false_positives']:<4} FN={m['false_negatives']:<4}")