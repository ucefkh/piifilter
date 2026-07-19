"""Check if any expected ADDRESS in the dataset has parenthetical after it."""
import json

data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']

for i, ex in enumerate(examples):
    text = ex['text']
    for ee in ex.get('entities', []):
        if ee['type'] == 'ADDRESS':
            end = ee['end']
            after = text[end:end+50]
            if '(' in after:
                print(f'Ex {i}: ADDRESS "{ee["value"]}" followed by: {repr(after[:40])}')