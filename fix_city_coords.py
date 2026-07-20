#!/usr/bin/env python3
"""Fix CITY labels so their coordinates match the deobfuscated text space."""
import json
import re

with open('benchmarks/data/pii_dataset.json') as f:
    dataset = json.load(f)

examples = dataset['examples']

# Recalculate CITY label coordinates by finding city names in the original text
# and matching to what the detector would find
for ex in examples:
    text = ex['text']
    entities = ex['entities']
    
    city_labels = [(i, e) for i, e in enumerate(entities) if e.get('type') == 'CITY']
    
    # For each CITY label, verify its start/end match text.index of its value
    for idx, e in city_labels:
        val = e['value']
        expected_start = text.index(val)
        expected_end = expected_start + len(val)
        if e['start'] != expected_start or e['end'] != expected_end:
            print(f"Fixing label '{val}' @ [{e['start']}:{e['end']}] -> [{expected_start}:{expected_end}] in: {text[:80]}")
            e['start'] = expected_start
            e['end'] = expected_end

with open('benchmarks/data/pii_dataset.json', 'w') as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)
print("All CITY label coordinates verified against original text.")
print("Dataset saved.")