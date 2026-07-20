#!/usr/bin/env python3
"""Check Springfield label in dataset."""
import json
with open('benchmarks/data/pii_dataset.json') as f:
    dataset = json.load(f)

for ex in dataset['examples']:
    text = ex['text']
    if 'Springfield' in text:
        print(f"Text: {text[:150]}")
        city_entities = [e for e in ex['entities'] if e.get('type') == 'CITY']
        for e in city_entities:
            print(f"  Label: type={e['type']}, value='{text[e['start']:e['end']]}' @ [{e['start']}:{e['end']}]")
        # Also check if there are any other entities at the Springfield position
        for e in ex['entities']:
            val = text[e['start']:e['end']]
            if 'Springfield' in val or val == 'Springfield':
                print(f"  Entity: type={e['type']}, value='{val}' @ [{e['start']}:{e['end']}]")