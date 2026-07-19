import json
from collections import Counter

from benchmarks.recall import is_masked_pii

data = json.loads(open('benchmarks/data/pii_dataset_v2.json').read())

masked = 0
real = 0
for ex in data['examples']:
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            if is_masked_pii(e):
                masked += 1
            else:
                real += 1

print(f"Real SSNs: {real}")
print(f"Masked/obfuscated SSNs: {masked}")
print(f"Total SSNs: {real + masked}")

# Show what's being classified as masked
print("\nClassified as MASKED:")
for ex in data['examples']:
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY' and is_masked_pii(e):
            print(f"  {repr(e['value'])}")

print("\nClassified as REAL:")
for ex in data['examples']:
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY' and not is_masked_pii(e):
            print(f"  {repr(e['value'])}")