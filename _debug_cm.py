"""Debug confusion matrix from recall-results.json"""
import json

data = json.load(open('benchmarks/recall-results.json'))
cm = data['detectors']['regex']['confusion_matrix']
print('Full confusion matrix:')
for expected, actuals in cm.items():
    for actual, count in actuals.items():
        print('  {:<20s} -> {:<20s} : {}'.format(expected, actual, count))
print()
# Also show per_type FP
pt = data['detectors']['regex']['per_type']
for et, metrics in sorted(pt.items()):
    fp = metrics['false_positives']
    fn = metrics['false_negatives']
    if fp > 0 or fn > 0:
        p = metrics['precision']
        r = metrics['recall']
        tp = metrics['true_positives']
        print('  {:<20s} p={:.4f} r={:.4f} TP={} FP={} FN={}'.format(et, p, r, tp, fp, fn))