#!/usr/bin/env python3
import json
data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data.get('examples', [])

# Count entity types
from collections import Counter
type_counts = Counter()
for ex in examples:
    for ent in ex.get('entities', []):
        type_counts[ent['type'].upper()] += 1

print("Entity type counts in dataset:")
for t, c in sorted(type_counts.items()):
    print(f"  {t:20s}: {c}")

print(f"\nTotal examples: {len(examples)}")
print(f"Total entities: {sum(type_counts.values())}")

# Show COUNTRY entries with more context
print("\n\n=== Full COUNTRY entries ===")
for idx, ex in enumerate(examples):
    for ent in ex.get('entities', []):
        if ent['type'].upper() == 'COUNTRY':
            text = ex['text']
            start, end = ent.get('start', 0), ent.get('end', 0)
            val = text[start:end]
            before = text[max(0,start-20):start]
            after = text[end:end+20]
            context = text[max(0,start-40):end+40]
            print(f"  #{idx}: |{before}[{val}]{after}|")
            print(f"         {context}")

# Show ADDRESS entries with full context
print("\n\n=== Full ADDRESS entries ===")
for idx, ex in enumerate(examples):
    for ent in ex.get('entities', []):
        if ent['type'].upper() == 'ADDRESS':
            text = ex['text']
            start, end = ent.get('start', 0), ent.get('end', 0)
            val = text[start:end]
            before = text[max(0,start-20):start]
            after = text[end:end+20]
            print(f"  #{idx}: |{before}[{val}]{after}|")
            print(f"         Full: {text}")