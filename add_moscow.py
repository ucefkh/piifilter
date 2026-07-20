#!/usr/bin/env python3
"""Re-add Moscow and check if it matches."""
import json

with open('benchmarks/data/pii_dataset.json') as f:
    dataset = json.load(f)

for ex in dataset['examples']:
    text = ex['text']
    if '37.6173 (Moscow)' in text:
        # Check if Moscow is already labeled
        found = False
        for e in ex['entities']:
            if e.get('type') == 'CITY' and e.get('value') == 'Moscow':
                found = True
                break
        if not found:
            idx = text.index('Moscow')
            ex['entities'].append({'type': 'CITY', 'value': 'Moscow', 'start': idx, 'end': idx + 6})
            print(f"Re-added CITY label for 'Moscow' @ [{idx}:{idx+6}]")

with open('benchmarks/data/pii_dataset.json', 'w') as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)
print("Done")