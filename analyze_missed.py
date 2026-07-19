#!/usr/bin/env python3
"""Analyze missed detections for target entity types."""
import json
import re
import sys
from pathlib import Path

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

# Load dataset
with open(PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset_v2.json") as f:
    data = json.load(f)

from piifilter_detector_regex.patterns import PATTERN_DEFS

# Compile all patterns
compiled = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    compiled.append((type_name, re.compile(raw_pattern, re.UNICODE), score))

target_types = ['DATE', 'URL', 'CUSTOMER_NAME', 'EMPLOYEE_NAME', 'IBAN', 
                'SSH_KEY', 'PROJECT_NAME', 'PASSPORT', 'PRIVATE_URL', 'BANK_ACCOUNT']

for target in target_types:
    print(f"\n{'='*70}")
    print(f"  {target}")
    print(f"{'='*70}")
    
    examples = []
    for item in data["examples"]:
        for ent in item["entities"]:
            if ent["type"] == target:
                examples.append((item["text"], ent))
    
    print(f"  Total examples: {len(examples)}")
    
    # Check which patterns match
    patterns_for_type = [(t, p, s) for t, p, s in compiled if t == target]
    print(f"  Patterns defined: {len(patterns_for_type)}")
    
    missed = 0
    for full_text, ent in examples:
        matched = False
        for _, pat, score in compiled:
            for m in pat.finditer(full_text):
                start, end = m.start(), m.end()
                # Check if this match overlaps with the entity
                if max(0, min(end, ent["end"]) - max(start, ent["start"])) / max(1, min(end - start, ent["end"] - ent["start"])) >= 0.5:
                    # Check type match
                    if _ == target:
                        matched = True
                        break
            if matched:
                break
        
        if not matched:
            missed += 1
            if missed <= 15:
                ctx_start = max(0, ent["start"] - 20)
                ctx_end = min(len(full_text), ent["end"] + 30)
                context = full_text[ctx_start:ctx_end]
                print(f"\n  MISSED: value={repr(ent['value']):<50}")
                print(f"          context={repr(context[:100])}")

print(f"\n\n{'='*70}")
print(f"  SUMMARY: Total missed per type")
print(f"{'='*70}")
for target in target_types:
    examples = []
    for item in data["examples"]:
        for ent in item["entities"]:
            if ent["type"] == target:
                examples.append((item["text"], ent))
    
    patterns_for_type = [(t, p, s) for t, p, s in compiled if t == target]
    
    missed = 0
    for full_text, ent in examples:
        matched = False
        for _, pat, score in compiled:
            for m in pat.finditer(full_text):
                start, end = m.start(), m.end()
                if max(0, min(end, ent["end"]) - max(start, ent["start"])) / max(1, min(end - start, ent["end"] - ent["start"])) >= 0.5:
                    if _ == target:
                        matched = True
                        break
            if matched:
                break
        if not matched:
            missed += 1
    
    total = len(examples)
    if total > 0:
        recall = (total - missed) / total * 100
        print(f"  {target:20s}: {total:4d} examples, {missed:4d} missed, recall={recall:.1f}%")