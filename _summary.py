import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
print(f"Regex: Precision={r['overall_precision']:.4f} Recall={r['overall_recall']:.4f} F1={r['overall_f1']:.4f}")
print()
issues = []
for et, m in sorted(r['per_type'].items()):
    status = "OK" if m['recall'] >= 0.95 and m['precision'] >= 0.85 else "ISSUE"
    if status == "ISSUE":
        issues.append((et, m))
    print(f"  {status:6s} {et:<20} precision={m['precision']:.4f} recall={m['recall']:.4f}")

print(f"\n{len(issues)} issues remaining:")