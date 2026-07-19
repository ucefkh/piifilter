import json
import re

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

# Find the specific examples for "192.168.1.1"
for example in data['examples']:
    for entity in example.get('entities', []):
        if entity['value'] == '192.168.1.1':
            print(repr(example['text']))
            print(f"  start={entity['start']}, end={entity['end']}")
            print(f"  context: {repr(example['text'][entity['start']-20:entity['end']+20])}")