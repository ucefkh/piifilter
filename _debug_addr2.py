import json
data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']
for idx in [95, 101, 1, 21, 44]:
    ex = examples[idx]
    print(f'=== Example {idx} ===')
    print('Text:', repr(ex['text']))
    print('Entities:', json.dumps(ex.get('entities', []), indent=2))
    print()