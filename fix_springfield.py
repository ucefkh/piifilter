#!/usr/bin/env python3
"""Fix 'Springfield' label - it was truncated to 'Springfiel'."""
import json

with open('benchmarks/data/pii_dataset.json') as f:
    dataset = json.load(f)

for ex in dataset['examples']:
    text = ex['text']
    if 'Springfield' in text:
        for e in ex['entities']:
            val = text[e['start']:e['end']]
            if val == 'Springfiel':
                print(f"Fixed: 'Springfiel' -> 'Springfield' @ [{e['start']}:{e['end']}] -> [{e['start']}:{e['start']+11}]")
                e['end'] = e['start'] + 11
                e['value'] = 'Springfield'

with open('benchmarks/data/pii_dataset.json', 'w') as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)
print("Dataset saved.")