#!/usr/bin/env python3
"""Debug why PERSON 'Alice Johnson' is still FN in the benchmark."""
import json, sys, re
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')

from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType

# Replicate the benchmark's make_regex_adapter detection
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
    compiled = re.compile(raw_pattern, re.IGNORECASE)
    patterns.append((entity_type, compiled, score))

text = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com Phone: +1-555-123-4567"
print(f'Text: {repr(text)}')
print()

entities = []
seen_intervals = []
for entity_type, pattern, score in patterns:
    for match in pattern.finditer(text):
        start, end = match.start(), match.end()
        if start == end:
            continue
        if any(s <= start and end <= e for s, e in seen_intervals):
            continue
        entities.append({
            "entity_type": entity_type.value,
            "value": match.group(),
            "start": start,
            "end": end,
            "score": score,
            "detector": "regex",
        })
        seen_intervals.append((start, end))
entities.sort(key=lambda e: e["start"])

print('Detected entities:')
for e in entities:
    print(f'  [{e["start"]}:{e["end"]}] {e["entity_type"]}={repr(e["value"][:40])} score={e["score"]}')

# Check if there's overlap with expected
expected = {"type": "PERSON", "value": "Alice Johnson", "start": 8, "end": 21}
print(f'\nExpected: PERSON={repr(expected["value"])} at [{expected["start"]}:{expected["end"]}]')
for e in entities:
    if e["entity_type"] == "PERSON":
        overlap_start = max(e["start"], expected["start"])
        overlap_end = min(e["end"], expected["end"])
        intersection = max(0, overlap_end - overlap_start)
        smallest = min(e["end"] - e["start"], expected["end"] - expected["start"])
        iou = intersection / smallest if smallest else 0
        print(f'  Detected PERSON at [{e["start"]}:{e["end"]}] = {repr(e["value"])}')
        print(f'  Overlap: int={intersection}, smallest={smallest}, iou={iou}')
    
    # Also check if any detection overlaps the span
    if e["start"] <= expected["start"] < e["end"] or e["start"] < expected["end"] <= e["end"]:
        print(f'  Overlapping detection: {e["entity_type"]} at [{e["start"]}:{e["end"]}] = {repr(e["value"][:40])}')
        if e["entity_type"] == "COMPANY":
            print(f'  -> THIS IS A COMPANY MATCH STEALING THE PERSON SPAN!')