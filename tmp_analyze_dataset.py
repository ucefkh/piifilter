import json
import sys
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/core/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src')

import subprocess
import tempfile
import os

# Load the full dataset
with open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

examples = data.get('examples', [])
print(f"Dataset: {len(examples)} examples")

# Count entities per type
from collections import Counter
type_counts = Counter()
for ex in examples:
    for ent in ex.get('entities', []):
        type_counts[ent.get('type', 'UNKNOWN')] += 1

print(f"Total entities: {sum(type_counts.values())}")
for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

# The task mentions "498 tests" - this is likely referring to the 
# total detection tests across all domains the pipeline runs 
# (TP + FN in the benchmark runs)