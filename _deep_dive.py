#!/usr/bin/env python3
"""Deep dive into remaining regex FNs and FPs."""
import json
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
import re

data = json.load(open('benchmarks/data/pii_dataset.json'))

_DIRECT_MAP = {"PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
    "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
    "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
    "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
    "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH"}

type_map = {"SSN": "SOCIAL_SECURITY", "API_KEY": "API_KEY", "JWT": "JWT",
    "EMAIL": "EMAIL", "PHONE": "PHONE", "CREDIT_CARD": "CREDIT_CARD",
    "IP_ADDRESS": "IP_ADDRESS", "DATABASE_URL": "DATABASE_URL",
    "DOMAIN": "DOMAIN", "PRIVATE_URL": "PRIVATE_URL", "IBAN": "IBAN",
    "BANK_ACCOUNT": "BANK_ACCOUNT", "PASSPORT": "PASSPORT",
    "SSH_KEY": "SSH_KEY", "GPS": "GPS", "FILE_PATH": "FILE_PATH"}

from piifilter.shared.models import EntityType

patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name in _DIRECT_MAP:
        et_name = type_name
    else:
        et_name = type_map.get(type_name, type_name.upper())
    try:
        entity_type = EntityType(et_name)
    except ValueError:
        entity_type = EntityType("PERSON")
    compiled = re.compile(raw_pattern, re.UNICODE)
    patterns.append((entity_type, compiled, score))

# Track FNs by type
fn_by_type = {}
fp_by_type = {}

for ex_idx, ex in enumerate(data["examples"]):
    text = ex["text"]
    expected = []
    for ent in ex["entities"]:
        expected.append({"type": ent["type"], "value": ent["value"],
                         "start": ent["start"], "end": ent["end"]})
    
    detected = []
    seen_intervals = []
    for entity_type, pattern, score in patterns:
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if start == end:
                continue
            if any(s <= start and end <= e for s, e in seen_intervals):
                continue
            detected.append({
                "entity_type": entity_type.value,
                "value": match.group(),
                "start": start,
                "end": end,
                "score": score,
            })
            seen_intervals.append((start, end))
    
    detected.sort(key=lambda e: e["start"])
    
    # Check FNs
    for exp in expected:
        found = False
        for det in detected:
            if det["entity_type"] != exp["type"]:
                continue
            overlap_start = max(det["start"], exp["start"])
            overlap_end = min(det["end"], exp["end"])
            intersection = max(0, overlap_end - overlap_start)
            smallest = min(det["end"] - det["start"], exp["end"] - exp["start"])
            if smallest > 0 and intersection / smallest >= 0.5:
                found = True
                break
        if not found:
            t = exp["type"]
            if t not in fn_by_type:
                fn_by_type[t] = []
            fn_by_type[t].append((ex_idx, text, exp))
    
    # Check FPs
    det_set = {d["entity_type"]: d for d in detected}
    for det in detected:
        found = False
        for exp in expected:
            if det["entity_type"] != exp["type"]:
                continue
            overlap_start = max(det["start"], exp["start"])
            overlap_end = min(det["end"], exp["end"])
            intersection = max(0, overlap_end - overlap_start)
            smallest = min(det["end"] - det["start"], exp["end"] - exp["start"])
            if smallest > 0 and intersection / smallest >= 0.5:
                found = True
                break
        if not found:
            t = det["entity_type"]
            if t not in fp_by_type:
                fp_by_type[t] = []
            fp_by_type[t].append((ex_idx, text, det))

print("=== FALSE NEGATIVES by Type ===")
for t in sorted(fn_by_type.keys()):
    print(f"\n  {t}: {len(fn_by_type[t])}")
    for ex_idx, text, exp in fn_by_type[t][:5]:
        context_start = max(0, exp["start"] - 20)
        context_end = min(len(text), exp["end"] + 20)
        ctx = text[context_start:context_end]
        if context_start > 0: ctx = "..." + ctx
        if context_end < len(text): ctx = ctx + "..."
        print(f"    Ex {ex_idx}: expected {t}='{exp['value']}' at [{exp['start']}:{exp['end']}]")
        print(f"      Context: {repr(ctx)}")

print("\n=== FALSE POSITIVES by Type ===")
for t in sorted(fp_by_type.keys()):
    print(f"\n  {t}: {len(fp_by_type[t])}")
    for ex_idx, text, det in fp_by_type[t][:5]:
        print(f"    Ex {ex_idx}: detected {t}='{det['value'][:40]}' at [{det['start']}:{det['end']}]")
        print(f"      Score={det['score']}")