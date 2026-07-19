#!/usr/bin/env python3
import json
data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data.get('examples', [])

# Find all COUNTRY entities that were expected
print("=== COUNTRY entities in dataset ===")
country_examples = []
for idx, ex in enumerate(examples):
    for ent in ex.get('entities', []):
        if ent['type'].upper() == 'COUNTRY':
            text = ex['text']
            start, end = ent.get('start', 0), ent.get('end', 0)
            val = text[start:end]
            country_examples.append((idx, val, text))
            print(f"  #{idx}: '{val}' (in: {text[:80]})")

print()
print(f"Total COUNTRY entities: {len(country_examples)}")

print("\n\n=== ADDRESS entities in dataset ===")
address_examples = []
for idx, ex in enumerate(examples):
    for ent in ex.get('entities', []):
        if ent['type'].upper() == 'ADDRESS':
            text = ex['text']
            start, end = ent.get('start', 0), ent.get('end', 0)
            val = text[start:end]
            address_examples.append((idx, val, text))
            print(f"  #{idx}: '{val}' (in: {text[:80]})")

print(f"\nTotal ADDRESS entities: {len(address_examples)}")