import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
print('=== OVERALL ===')
print(f"Precision: {r['overall_precision']:.4f}  Recall: {r['overall_recall']:.4f}  F1: {r['overall_f1']:.4f}")
print()
print('=== PER TYPE ===')
print(f"{'Type':<20} {'Precision':<10} {'Recall':<10} {'F1':<10} {'TP':<6} {'FP':<6} {'FN':<6}")
print('-' * 80)
for et, m in sorted(r['per_type'].items()):
    print(f"{et:<20} {round(m['precision'],4):<10} {round(m['recall'],4):<10} {round(m['f1'],4):<10} {m['true_positives']:<6} {m['false_positives']:<6} {m['false_negatives']:<6}")