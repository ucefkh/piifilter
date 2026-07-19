import json
data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']
for i in [22]:
    ex = examples[i]
    print(f'Ex {i} text:', repr(ex['text']))
    print(f'Ex {i} entities:', json.dumps(ex.get('entities',[]), indent=2))