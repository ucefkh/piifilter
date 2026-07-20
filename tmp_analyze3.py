#!/usr/bin/env python3
"""Analyze adversarial v3 dataset for CC/SSN."""
import json, re
from collections import Counter

path = "/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/adversarial_v3.json"
with open(path) as f:
    data = json.load(f)

examples = data["examples"]
print(f"Total examples: {len(examples)}")
print(f"Entity types: {data.get('entity_types')}")

# Count by type
type_counts = Counter()
for ex in examples:
    text = ex["text"]
    for e in ex.get("entities", []):
        type_counts[e["type"]] += 1
for t, c in type_counts.most_common():
    print(f"  {t}: {c}")

# Show CC and SSN examples - full context
print("\n=== CREDIT_CARD examples ===")
for ex in examples:
    for e in ex.get("entities", []):
        if e["type"] == "CREDIT_CARD":
            text = ex["text"]
            start, end = e["start"], e["end"]
            span = text[start:end]
            ctx_before = text[max(0,start-50):start]
            ctx_after = text[end:end+50]
            digits = re.sub(r"[^0-9]", "", span)
            print(f"\n  span={span!r}")
            print(f"  digits={digits:20s} len={len(digits)}")
            print(f"  ctx='{ctx_before}|{ctx_after}'")

print("\n=== SOCIAL_SECURITY examples ===")
for ex in examples:
    for e in ex.get("entities", []):
        if e["type"] == "SOCIAL_SECURITY":
            text = ex["text"]
            start, end = e["start"], e["end"]
            span = text[start:end]
            ctx_before = text[max(0,start-50):start]
            ctx_after = text[end:end+50]
            digits = re.sub(r"[^0-9]", "", span)
            print(f"\n  span={span!r}")
            print(f"  digits={digits:20s} len={len(digits)}")
            print(f"  ctx='{ctx_before}|{ctx_after}'")