import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
print(f"Overall: Precision={r['overall_precision']:.4f} Recall={r['overall_recall']:.4f} F1={r['overall_f1']:.4f}")
print()
for et, m in sorted(r['per_type'].items()):
    print(f"{et:<20} precision={m['precision']:.4f} recall={m['recall']:.4f} f1={m['f1']:.4f} TP={m['true_positives']:<4} FP={m['false_positives']:<4} FN={m['false_negatives']:<4}")