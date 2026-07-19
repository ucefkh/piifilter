import json

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)
items = data['examples']
print(f'Total examples: {len(items)}')

# Find all IP_ADDRESS entities and their values
ip_entries = []
for example in items:
    for entity in example.get('entities', []):
        if entity['type'] == 'IP_ADDRESS':
            ip_entries.append({
                'text': example['text'],
                'value': entity['value'],
                'start': entity['start'],
                'end': entity['end']
            })
print(f'Total IP_ADDRESS entries: {len(ip_entries)}')

# Show value distribution to understand variants
from collections import Counter
value_counts = Counter(e['value'] for e in ip_entries)
print(f'Unique IP values: {len(value_counts)}')
for v, c in value_counts.most_common(100):
    print(f'  [{c:3d}x] {repr(v)}')