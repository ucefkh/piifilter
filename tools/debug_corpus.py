"""Debug the overall scoring to see how MASKED_SSN FP is counted."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import json
corpus = json.load(open('benchmarks/data/golden_corpus.json'))
examples = corpus['examples']

# Find example 179
ex = examples[179]
print(f"Example 179 text: {repr(ex['text'])}")
print(f"Golden entities: {ex['entities']}")
print(f"Golden types: {[e['type'] for e in ex['entities']]}")

# Count all golden by type
from collections import Counter
all_types = Counter()
for ex in examples:
    for e in ex.get('entities', []):
        all_types[e['type']] += 1
        
print(f"\nAll golden types: {dict(all_types)}")
print(f"MASKED_SSN in golden: {all_types.get('MASKED_SSN', 0)}")