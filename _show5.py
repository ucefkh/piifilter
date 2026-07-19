import json
with open('benchmarks/recall-results.json') as f:
    d = json.load(f)
r = d['detectors']['regex']
cm = r['confusion_matrix']
print("Confusion:")
for exp, acts in sorted(cm.items()):
    for act, cnt in sorted(acts.items()):
        print(f"  Expected={exp:20s} -> Detected={act:20s}: {cnt}")