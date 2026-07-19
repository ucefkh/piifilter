import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
print("=== FALSE NEGATIVES ANALYSIS ===")
print(f"Total FN: {r['total_false_negatives']}")
print()
print("--- Types below recall 0.95 ---")
for et, m in sorted(r['per_type'].items()):
    if m['recall'] < 0.95 or m['precision'] < 0.85:
        print(f"{et}: recall={m['recall']:.4f} precision={m['precision']:.4f} FN={m['false_negatives']} FP={m['false_positives']}")

print()
print("=== CONFUSION MATRIX ===")
for expected, actuals in sorted(r['confusion_matrix'].items()):
    for actual, count in sorted(actuals.items()):
        print(f"  Expected={expected:20s} -> Detected={actual:20s}: {count}")

print()
print("=== EXAMPLE FAILURES (FN or FP) ===")
for ex in r['example_results']:
    if ex['false_positives'] > 0 or ex['false_negatives'] > 0:
        print(f"\n  Example {ex['index']}:")
        print(f"    Text: {ex['text_preview']}")
        print(f"    Expected: {ex['expected']} entities ({ex['expected_types']})")
        print(f"    Detected: {ex['detected']} entities ({ex['detected_types']})")
        print(f"    TP={ex['true_positives']} FP={ex['false_positives']} FN={ex['false_negatives']}")