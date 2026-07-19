"""Analyze EMAIL false negatives in the PII dataset."""
import json
import sys
import re
from pathlib import Path

# Load the dataset
dataset_path = Path("benchmarks/data/pii_dataset_v2.json")
data = json.loads(dataset_path.read_text())

# Current pattern
current_pattern = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b', re.UNICODE)

# Collect all EMAIL entities with their example texts
email_fns = []
email_tps = []
for ex in data["examples"]:
    text = ex["text"]
    for ent in ex["entities"]:
        if ent["type"] != "EMAIL":
            continue
        value = ent["value"].lower()
        # Check if the current pattern matches the value directly
        if current_pattern.search(value):
            email_tps.append(value)
        else:
            email_fns.append({"text": text, "value": value, "start": ent["start"], "end": ent["end"]})

print(f"Total EMAIL entities: {len(email_tps) + len(email_fns)}")
print(f"True Positives (matched directly): {len(email_tps)}")
print(f"False Negatives (missed directly): {len(email_fns)}")
print(f"\nDirect EMAIL recall: {len(email_tps) / (len(email_tps) + len(email_fns)):.4f}")

print("\n" + "="*80)
print("FALSE NEGATIVES — EMAIL values missed by current pattern:")
print("="*80)

# Categorize them
categories = {
    "long_TLD": [],
    "plus_tag": [],
    "subdomain_multi_tld": [],
    "quoted": [],
    "obfuscated": [],
    "other": [],
}

for fn in email_fns:
    v = fn["value"]
    if "+" in v.split("@")[0] if "@" in v else False:
        categories["plus_tag"].append(fn)
    elif v.count(".") >= 3:  # user@sub.domain.co.uk style
        categories["subdomain_multi_tld"].append(fn)
    elif len(v.split(".")[-1]) > 4:  # long TLD
        categories["long_TLD"].append(fn)
    elif '"' in v or "'" in v:
        categories["quoted"].append(fn)
    else:
        # Check for obfuscated
        if any(c in v for c in ["[at]", "[dot]", " AT ", " DOT ", " at ", " dot "]):
            categories["obfuscated"].append(fn)
        else:
            categories["other"].append(fn)

total_fns = len(email_fns)
for cat, items in categories.items():
    print(f"\n── {cat.upper()}: {len(items)}/{total_fns}")
    for fn in items[:10]:
        print(f"  VALUE: {fn['value']}")
        print(f"  TEXT: {fn['text'][:120]}")
        print()

# Deeper analysis: what exactly in the pattern fails?
print("\n" + "="*80)
print("DETAILED ANALYSIS OF MISSED EMAILS:")
print("="*80)

for fn in email_fns[:30]:
    v = fn["value"]
    parts = v.split("@")
    if len(parts) != 2:
        print(f"  SKIP (no @): {v}")
        continue
    local, domain = parts
    domain_parts = domain.split(".")
    tld = domain_parts[-1] if domain_parts else ""
    
    issues = []
    if "+" in local:
        issues.append(f"PLUS_TAG (local='{local}')")
    if len(tld) > 4:
        issues.append(f"LONG_TLD (tld='{tld}')")
    if len(domain_parts) > 2:
        issues.append(f"MULTI_DOMAIN (domain='{domain}', parts={len(domain_parts)})")
    
    print(f"  EMAIL: {v}")
    if issues:
        for i in issues:
            print(f"    -> {i}")
    else:
        # Just test the regex
        m = current_pattern.search(v)
        if m:
            print(f"    -> Actually MATCHES: '{m.group()}'")
        else:
            print(f"    -> FAILS for unknown reason")
    print()