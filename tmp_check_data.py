import json
with open('benchmarks/data/ood_corpus_v1.json') as f:
    data = json.load(f)
print('keys:', list(data.keys()))
ex0 = data['examples'][0]
print('type:', type(ex0))
print('item:', json.dumps(ex0, indent=2)[:500])