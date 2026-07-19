import json
data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']
for i, ex in enumerate(examples):
    for ent in ex.get('entities', []):
        if ent['type'] == 'ADDRESS':
            print(f'Ex {i}: "{ent["value"]}" — context: ...{ex["text"][max(0,ent["start"]-40):ent["end"]+20]}...')