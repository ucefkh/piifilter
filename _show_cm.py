#!/usr/bin/env python3
import json
data = json.load(open('benchmarks/recall-results.json'))
print('Confusion matrix (regex):')
cm = data['detectors']['regex']['confusion_matrix']
for expected, actuals in sorted(cm.items()):
    for actual, count in sorted(actuals.items()):
        print(f'  Expected {expected:20s} -> got {actual:20s} (count={count})')