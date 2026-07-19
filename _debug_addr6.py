import json
data = json.loads(open('benchmarks/data/pii_dataset.json').read())
ex = data['examples'][101]
print(f'Text: {repr(ex["text"])}')
print(f'Entities: {json.dumps(ex.get("entities",[]), indent=2)}')