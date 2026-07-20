#!/usr/bin/env python3
"""Directly check each CITY example against the regex patterns using re module."""
import sys, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.patterns import PATTERN_DEFS

# Load dataset
import json
with open(str(PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset.json")) as f:
    data = json.load(f)
examples = data["examples"] if isinstance(data, dict) and "examples" in data else data

# Get all CITY patterns
city_patterns = [(i, pat, conf) for i, (etype, pat, conf) in enumerate(PATTERN_DEFS) if etype == "CITY"]
print(f"=== {len(city_patterns)} CITY patterns ===")

# Test each example
print("\n=== Testing each CITY example ===")
for i, ex in enumerate(examples):
    text = ex["text"]
    expected_cities = [e for e in ex.get("entities", []) if e["type"] == "CITY"]
    if not expected_cities:
        continue
    
    # Try each pattern
    all_matches = []
    for pat_idx, pattern, conf in city_patterns:
        try:
            for m in re.finditer(pattern, text):
                all_matches.append((pat_idx, m.start(), m.end(), m.group(), conf))
        except re.error as e:
            print(f"  ERROR pat[{pat_idx}]: {e}")
    
    for exp in expected_cities:
        found = any(s == exp["start"] and e == exp["end"] for _, s, e, _, _ in all_matches)
        status = "OK" if found else "FN"
        if not found:
            print(f"\n  [{i:3d}] {status}: expected '{exp['value']}' [{exp['start']}:{exp['end']}]")
            print(f"         text: '{text}'")
            for pat_idx, s, e, g, conf in all_matches:
                print(f"         MATCH pat[{pat_idx}] '{g}' [{s}:{e}] conf={conf:.2f}")
        else:
            print(f"  [{i:3d}] OK: '{exp['value']}' [{exp['start']}:{exp['end']}]")
    
    for pat_idx, s, e, g, conf in all_matches:
        expected_match = any(s == exs["start"] and e == exs["end"] for exs in expected_cities)
        if not expected_match:
            print(f"  [{i:3d}] FP: pat[{pat_idx}] '{g}' [{s}:{e}] conf={conf:.2f}")