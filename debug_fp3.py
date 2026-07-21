"""Debug what PERSON entities are being suppressed — check the FNs."""
import json
with open('benchmarks/recall-results-heldout-arb.json') as f:
    data = json.load(f)

pa = data['detectors'].get('pipeline-arbitration', {})
person = pa.get('per_type', {}).get('PERSON', {})
print(f"PERSON: TP={person['true_positives']}, FP={person['false_positives']}, FN={person['false_negatives']}")
print(f"n_total={person['n_total']}, precision={person['precision']}, recall={person['recall']}")

# Look at all FP examples from ALL types to see what changed
# Let's check pipeline-raw PERSON to see the original FPs vs pipeline-arbitration
raw = data['detectors'].get('pipeline-raw', {})
raw_person = raw.get('per_type', {}).get('PERSON', {})
print(f"\nPIPELINE-RAW PERSON: TP={raw_person['true_positives']}, FP={raw_person['false_positives']}, FN={raw_person['false_negatives']}")
print(f"  precision={raw_person['precision']}, recall={raw_person['recall']}")