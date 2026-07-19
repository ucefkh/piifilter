import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
print(f"Overall: Precision={r['overall_precision']:.4f} Recall={r['overall_recall']:.4f}")
print()
for et, m in sorted(r['per_type'].items()):
    if m['recall'] < 1.0 or m['precision'] < 0.85:
        print(f"ISSUE: {et:<20} precision={m['precision']:.4f} recall={m['recall']:.4f} TP={m['true_positives']} FP={m['false_positives']} FN={m['false_negatives']}")