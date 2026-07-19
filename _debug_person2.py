import json, re, sys

sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']

for idx in [45, 71, 105, 114]:
    ex = examples[idx]
    print(f'=== Ex {idx} ===')
    print(f'Text: {repr(ex["text"])}')
    print(f'Expected: {json.dumps(ex["entities"], indent=2)}')
    print()