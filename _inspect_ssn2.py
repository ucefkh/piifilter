"""Inspect SSN examples: focus on format patterns."""
import json
import re

data = json.load(open('benchmarks/data/pii_dataset_v2.json'))
ssn_examples = [ex for ex in data['examples'] if any(e['type'] == 'SOCIAL_SECURITY' for e in ex.get('entities', []))]

# Categorize by format
formats = {}
for i, ex in enumerate(ssn_examples):
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            val = e['value']
            key = f'fmt_{len(val)}' 
            digits = re.sub(r'[^0-9X*]', '', val)
            print(f'  [{i:3d}] text={repr(ex["text"][:100]):<105} value={repr(val):<40} digits={repr(digits)}')

print(f'\nTotal SSN examples: {len(ssn_examples)}')