import json, sys
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/core/src')

for name in ['pii_dataset.json', 'pii_dataset_v2.json']:
    with open(f'/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/{name}') as f:
        data = json.load(f)
    ex = data.get('examples', [])
    total_entities = sum(len(e.get('entities', [])) for e in ex)
    print(f'{name}: {len(ex)} examples, {total_entities} entities')

import glob
for f in sorted(glob.glob('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/adversarial*.json')):
    with open(f) as fh:
        data = json.load(fh)
    ex = data.get('examples', [])
    total_entities = sum(len(e.get('entities', [])) for e in ex)
    print(f'{f.split("/")[-1]}: {len(ex)} examples, {total_entities} entities')