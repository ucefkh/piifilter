#!/usr/bin/env python3
import json
data = json.load(open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/pii_dataset.json'))
print("type:", type(data))
if isinstance(data, dict):
    print("keys:", list(data.keys())[:10])
elif isinstance(data, list):
    print("len:", len(data))
    first = data[0]
    print("first type:", type(first))
    if isinstance(first, str):
        print("first:", first[:200])
    else:
        print("first:", json.dumps(first, indent=2)[:500])