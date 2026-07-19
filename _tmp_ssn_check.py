import json
from collections import Counter

data = json.loads(open('benchmarks/data/pii_dataset_v2.json').read())
ssns = []
for ex in data['examples']:
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            ssns.append(e['value'])
print(f'Total SSNs: {len(ssns)}')
for val, cnt in sorted(Counter(ssns).items(), key=lambda x: -x[1])[:50]:
    print(f'  {cnt:3d}x  {repr(val)}')