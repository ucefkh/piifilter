"""Analyze all PHONE samples in the dataset."""
import json

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

examples = data['examples']
phones = [(i, item) for i, item in enumerate(examples) for e in item.get('entities', []) if e.get('type') == 'PHONE']

print(f'Total PHONE samples: {len(phones)}\n')

# Categorize each phone
categories = {}
for idx, item in phones:
    for e in item.get('entities', []):
        if e.get('type') == 'PHONE':
            text = e.get('value', '')
            if text.startswith('+'):
                cat = 'international_plus'
            elif text.startswith('00'):
                cat = 'international_double_zero'
            elif text.startswith('0'):
                cat = 'local_zero_lead'
            elif text[0].isdigit():
                cat = 'other_digit'
            else:
                cat = 'other'
            
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(text)

for cat, samples in sorted(categories.items()):
    print(f'\n=== {cat} ({len(samples)} samples) ===')
    for s in sorted(set(samples)):
        print(f'  "{s}"')