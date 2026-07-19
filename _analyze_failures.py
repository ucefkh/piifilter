#!/usr/bin/env python3
"""Analyze benchmark failures to guide pattern fixes."""
import json

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

# Extract all failing types
for type_name in ['CITY', 'PERSON', 'GPS', 'CUSTOMER_NAME', 'EMPLOYEE_NAME', 'BANK_ACCOUNT']:
    print(f'\n{"="*60}')
    print(f'  {type_name} examples')
    print(f'{"="*60}')
    for i, ex in enumerate(examples):
        for e in ex['entities']:
            if e['type'] == type_name:
                print(f'  Ex {i}: entity={e}, text_snippet={repr(ex["text"][max(0,e["start"]-20):e["end"]+20])}')
                print(f'    full: {repr(ex["text"][:120])}')

# Also check what regex actually detects vs labeled
print(f'\n{"="*60}')
print('  Analyzing common false positives')
print(f'{"="*60}')

# Look at URL-like examples to understand DOMAIN/PRIVATE_URL overlap
for i, ex in enumerate(examples):
    for e in ex['entities']:
        if e['type'] in ('DOMAIN', 'PRIVATE_URL', 'DATABASE_URL', 'EMAIL'):
            # check if there are overlapping patterns
            print(f'  Ex {i} [{e["type"]}]: {repr(ex["text"][e["start"]:e["end"]])}')