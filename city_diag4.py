#!/usr/bin/env python3
"""Test each CITY pattern against FN cases using actual patterns from the module."""
import sys, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))
from piifilter_detector_regex.patterns import PATTERN_DEFS

city_patterns = [(i, pat, conf) for i, (etype, pat, conf) in enumerate(PATTERN_DEFS) if etype == "CITY"]
print(f"=== {len(city_patterns)} CITY patterns ===")
for idx, pat, conf in city_patterns:
    print(f"  [{idx}] conf={conf:.2f}: {pat[:80]}...")

fn_texts = [
    ("Example 1", "Our office is at 350 Fifth Avenue, New York, NY 10118", 35, 43),
    ("Example 2", "Paris has a population of over 2 million people and is the capital of France.", 0, 5),
    ("Example 21", "Visit us at 10 Downing Street, London, SW1A 2AA", 31, 37),
]

for name, text, exp_s, exp_e in fn_texts:
    print(f"\n=== {name}: '{text[:60]}...' ===")
    for idx, pat, conf in city_patterns:
        try:
            for m in re.finditer(pat, text):
                # Check for exact match
                exact = m.start() == exp_s and m.end() == exp_e
                marker = "***EXACT***" if exact else ""
                print(f"  [{idx}] conf={conf:.2f} '{m.group()}' [{m.start()}:{m.end()}] {marker}")
        except re.error as e:
            print(f"  [{idx}] ERROR: {e}")
    print()