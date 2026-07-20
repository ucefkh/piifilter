#!/usr/bin/env python3
"""Analyze adversarial v3 dataset for CC/SSN."""
import json, re, sys

path = "/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/adversarial_v3.json"
with open(path) as f:
    data = json.load(f)
print(f"Type: {type(data)}")
if isinstance(data, list):
    if data:
        ex = data[0]
        print(f"First element type: {type(ex)}")
        if isinstance(ex, dict):
            print(f"Keys: {list(ex.keys())}")
        elif isinstance(ex, str):
            # It's a JSONL-like list of strings - try parsing first line
            print(f"First element is a string, len={len(ex)}, preview: {ex[:200]}")
    print(f"Total items: {len(data)}")
elif isinstance(data, dict):
    print(f"Keys: {list(data.keys())[:20]}")