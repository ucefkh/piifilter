#!/usr/bin/env python3
"""List all CITY examples from the benchmark dataset."""
import json

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)
examples = data['examples'] if isinstance(data, dict) and 'examples' in data else data
city_examples = []
for i, ex in enumerate(examples):
    for ent in ex.get('entities', []):
        if ent['type'] == 'CITY':
            city_examples.append({'idx': i, 'text': ex['text'], 'value': ent['value'], 'start': ent['start'], 'end': ent['end']})
print(f'Found {len(city_examples)} CITY examples')
for c in city_examples:
    print(f'  [{c["idx"]}] "{c["text"]}" -> CITY({c["value"]}) [{c["start"]}:{c["end"]}]')