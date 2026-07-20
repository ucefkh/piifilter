#!/usr/bin/env python3
"""Directly check each CITY example against the regex patterns."""
import sys, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.models import EntityType

# Load dataset
import json
with open(str(PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset.json")) as f:
    data = json.load(f)
examples = data["examples"] if isinstance(data, dict) and "examples" in data else data

detector = RegexDetector()

# Get all CITY patterns from patterns.py
from piifilter_detector_regex.patterns import PATTERN_DEFS
city_patterns = [(i, pat, conf) for i, (etype, pat, conf) in enumerate(PATTERN_DEFS) if etype == "CITY"]
print(f"=== {len(city_patterns)} CITY patterns ===")

# Test each example
print("\n=== Testing each CITY example ===")
for i, ex in enumerate(examples):
    text = ex["text"]
    expected_cities = [e for e in ex.get("entities", []) if e["type"] == "CITY"]
    if not expected_cities:
        continue
    
    candidates = detector.detect(text)
    city_candidates = [c for c in candidates if c.entity_type == EntityType.CITY]
    
    for exp in expected_cities:
        found = any(c.start == exp["start"] and c.end == exp["end"] for c in city_candidates)
        status = "OK" if found else "FN"
        if not found:
            # Show which patterns matched what
            print(f"\n  [{i:3d}] {status}: expected '{exp['value']}' [{exp['start']}:{exp['end']}]")
            print(f"         text: '{text}'")
            for pat_idx, pattern, conf in city_patterns:
                for m in re.finditer(pattern, text):
                    print(f"         MATCH pat[{pat_idx}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        else:
            print(f"  [{i:3d}] OK: '{exp['value']}' [{exp['start']}:{exp['end']}]")
    
    for c in city_candidates:
        expected_match = any(c.start == e["start"] and c.end == e["end"] for e in expected_cities)
        if not expected_match:
            print(f"  [{i:3d}] FP: got '{c.value}' [{c.start}:{c.end}] score={c.confidence:.3f}")