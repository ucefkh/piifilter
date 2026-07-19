"""Inspect SSN examples in the benchmark dataset."""
import json

data = json.load(open('benchmarks/data/pii_dataset_v2.json'))
ssn_examples = [ex for ex in data['examples'] if any(e['type'] == 'SOCIAL_SECURITY' for e in ex.get('entities', []))]
for i, ex in enumerate(ssn_examples[:30]):
    print(f'--- Example {i} ---')
    print(f'Text: {repr(ex["text"][:150])}')
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            print(f'  -> SSN value: {repr(e["value"])}')
    print()
print(f'Total SSN examples: {len(ssn_examples)}')