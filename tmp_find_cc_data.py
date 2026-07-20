#!/usr/bin/env python3
"""Find which datasets have CC/SSN examples."""
import json
from pathlib import Path

datasets = list(Path("/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data").glob("*.json"))
for ds_path in sorted(datasets):
    with open(ds_path) as f:
        try:
            data = json.load(f)
        except:
            print(f"{ds_path.name}: parse error")
            continue
    
    if isinstance(data, dict):
        examples = data.get("examples", [])
        if not examples:
            examples = data.get("records", [])
    elif isinstance(data, list):
        examples = data
    else:
        print(f"{ds_path.name}: unknown format {type(data)}")
        continue
    
    cc_count = 0
    ssn_count = 0
    total = len(examples)
    for ex in examples:
        if isinstance(ex, str):
            continue
        for e in ex.get("entities", []):
            t = e.get("type", "")
            if t == "CREDIT_CARD":
                cc_count += 1
            elif t == "SOCIAL_SECURITY":
                ssn_count += 1
    
    total_entities = sum(len(ex.get("entities", [])) for ex in examples if isinstance(ex, dict))
    print(f"{ds_path.name}: {total} examples, {total_entities} entities, CC={cc_count}, SSN={ssn_count}")