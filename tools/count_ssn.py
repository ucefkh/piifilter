import json
corpus = json.load(open('benchmarks/data/golden_corpus.json'))
examples = corpus['examples']
count = 0
for i, ex in enumerate(examples):
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            count += 1
            if i == 179:
                print(f'Example 179 SOCIAL_SECURITY: {e}')
print(f'Total SOCIAL_SECURITY in golden: {count}')