#!/usr/bin/env python3
"""Analyze CC/SSN examples from the main datasets."""
import json, re
from pathlib import Path

base = Path("/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data")

datasets = ["pii_dataset_v2.json", "pii_dataset.json", "golden_corpus.json"]

for ds_name in datasets:
    with open(base / ds_name) as f:
        data = json.load(f)
    if isinstance(data, dict):
        examples = data.get("examples", data.get("records", []))
    else:
        examples = data
    
    print(f"\n{'='*80}")
    print(f"=== {ds_name} ===")
    
    for ex in examples:
        if isinstance(ex, str):
            continue
        for e in ex.get("entities", []):
            if e["type"] in ("CREDIT_CARD", "SOCIAL_SECURITY"):
                text = ex["text"]
                start, end = e["start"], e["end"]
                span = text[start:end]
                ctx_before = text[max(0,start-30):start]
                ctx_after = text[end:end+30]
                digits = re.sub(r"[^0-9]", "", span)
                
                # Check what deobfuscator does
                from piifilter.shared.deobfuscator import Deobfuscator
                deob = Deobfuscator()
                cleaned, log, gps_text = deob(text)
                stripped = Deobfuscator._strip_inner_separators(cleaned)
                
                # Does it appear in stripped?
                stripped_span = stripped[start:end] if end <= len(stripped) else "OUT_OF_BOUNDS"
                
                # Check Luhn
                from piifilter.shared.validation import _luhn_checksum
                luhn_cc = _luhn_checksum(digits) if e["type"] == "CREDIT_CARD" else None
                
                # Check SSN area
                area_ok = None
                if e["type"] == "SOCIAL_SECURITY" and len(digits) == 9:
                    area = int(digits[:3])
                    group = int(digits[3:5])
                    serial = int(digits[5:])
                    area_ok = not (area == 0 or area == 666 or area >= 900)
                    group_ok = group != 0
                    serial_ok = serial != 0
                    print(f"  [{e['type']}] span={span!r:45s} digits={digits:15s} area={area:3d} area_ok={area_ok} group={group:2d} group_ok={group_ok} serial={serial:4d} serial_ok={serial_ok}")
                else:
                    print(f"  [{e['type']}] span={span!r:45s} digits={digits:15s} luhn={luhn_cc} ctx='{ctx_before}|{ctx_after}'")
                
                # Check: would stripped text preserve the digit content?
                if stripped_span != "OUT_OF_BOUNDS":
                    stripped_digits = re.sub(r"[^0-9]", "", stripped_span)
                    if stripped_digits != digits:
                        print(f"    WARNING: stripped_digits={stripped_digits!r} != original digits={digits!r}")