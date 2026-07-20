"""Analyze adversarial v3 dataset for CC/SSN."""
import json, re
from collections import Counter
from pathlib import Path

path = Path("/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/adversarial_v3.json")
data = json.loads(path.read_text())
print(f"Total examples: {len(data)}")

# Count by type
type_counts = Counter()
for ex in data:
    for e in ex.get("entities", []):
        type_counts[e["type"]] += 1
for t, c in type_counts.most_common():
    print(f"  {t}: {c}")

# Show CC and SSN examples - full context
print("\n=== CREDIT_CARD examples ===")
for ex in data:
    for e in ex.get("entities", []):
        if e["type"] == "CREDIT_CARD":
            text = ex["text"]
            start, end = e["start"], e["end"]
            span = text[start:end]
            # Show context around the match
            ctx_before = text[max(0,start-30):start]
            ctx_after = text[end:end+30]
            digits = re.sub(r"[^0-9]", "", span)
            print(f"  span={span!r:50s} digits={digits:20s} ctx='{ctx_before}|{ctx_after}'")

print("\n=== SOCIAL_SECURITY examples ===")
for ex in data:
    for e in ex.get("entities", []):
        if e["type"] == "SOCIAL_SECURITY":
            text = ex["text"]
            start, end = e["start"], e["end"]
            span = text[start:end]
            ctx_before = text[max(0,start-30):start]
            ctx_after = text[end:end+30]
            digits = re.sub(r"[^0-9]", "", span)
            print(f"  span={span!r:50s} digits={digits:20s} ctx='{ctx_before}|{ctx_after}'")