#!/usr/bin/env python3
import json
d = json.load(open('benchmarks/recall-results.json'))
r = d['detectors']['regex']
print('expected:', r['total_expected_entities'], 'detected:', r['total_detected_entities'], 'TP:', r['total_true_positives'], 'FN:', r['total_false_negatives'])
print('Detector name:', r['detector'])
print('Keys:', list(r.keys()))