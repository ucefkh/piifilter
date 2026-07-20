import json

with open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)
ex = data.get('examples', [])
print(f"v2 dataset: {len(ex)} examples")

# Check splits in recall.py
with open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/recall.py') as f:
    content = f.read()
    
# Find test_size or split info
import re
for line in content.split('\n'):
    if 'test' in line.lower() and ('size' in line.lower() or 'split' in line.lower() or '0.' in line):
        print(f"  split line: {line.strip()}")