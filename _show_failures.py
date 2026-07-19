#!/usr/bin/env python3
import json
data = json.load(open('benchmarks/data/pii_dataset.json'))

indices_to_show = [22, 125, 127, 130, 132, 134, 136, 138, 143, 148, 149]

for idx in indices_to_show:
    ex = data['examples'][idx]
    print(f"\n{'='*60}")
    print(f"Example #{idx}")
    print(f"Text: {ex['text']!r}")
    for ent in ex.get('entities', []):
        start, end = ent.get('start', 0), ent.get('end', 0)
        val = ex['text'][start:end]
        print(f"  Entity: type={ent['type']:20s} span=({start},{end}) val={val!r}")