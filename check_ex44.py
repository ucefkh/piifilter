#!/usr/bin/env python3
"""Check example 44 in detail."""
import json
with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)
ex = data['examples'][44]
print('Text:', ex['text'])
print('Entities:')
for e in ex.get('entities', []):
    print(f'  {e["type"]}: "{e["value"]}" [{e["start"]}:{e["end"]}]')
# Check if Springfield is in the text
idx = ex['text'].find('Springfield')
print(f'\nSpringfield found at index: {idx}')
print(f'Text around Springfield: "{ex["text"][idx-5:idx+30]}"')