#!/usr/bin/env python3
import json
data = json.loads(open('benchmarks/data/pii_dataset_v2.json').read())
total_ssn = sum(1 for ex in data['examples'] for e in ex.get('entities', []) if e['type'] == 'SOCIAL_SECURITY')
print(f'Total examples: {len(data["examples"])}')
print(f'Total SSN entities: {total_ssn}')
formats = {}
for ex in data['examples']:
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            v = e['value']
            if '-' in v:
                fmt = 'hyphen'
            elif '\u00a0' in v:
                fmt = 'nbsp'
            elif '.' in v:
                fmt = 'dot'
            elif ' ' in v:
                fmt = 'space'
            elif v.isdigit():
                fmt = 'consecutive'
            else:
                fmt = 'other'
            formats[fmt] = formats.get(fmt, 0) + 1
print('Formats:', formats)