"""Focus on the 5 'other' FNs and any pattern-improvable cases."""
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path("core/src").resolve()))
sys.path.insert(0, str(Path("plugins/detector-regex/src").resolve()))

from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.deobfuscator import Deobfuscator

deob = Deobfuscator()

# Load the current pattern
current_pattern = None
for tn, rp, sc in PATTERN_DEFS:
    if tn == "EMAIL":
        current_pattern = re.compile(rp, re.UNICODE)
        print(f"CURRENT PATTERN: {rp}")
        break

# Load dataset
dataset_path = Path("benchmarks/data/pii_dataset_v2.json")
data = json.loads(dataset_path.read_text())

# Collect FNs with detail
fn_details = []
for ex in data["examples"]:
    text = ex["text"]
    cleaned, log = deob(text)
    
    for ent in ex["entities"]:
        if ent["type"] != "EMAIL":
            continue
        
        val = ent["value"]
        s, e = ent["start"], ent["end"]
        
        found = False
        for m in current_pattern.finditer(cleaned):
            ms, me = m.start(), m.end()
            overlap = min(e, me) - max(s, ms)
            smallest = min(e - s, me - ms)
            if smallest > 0 and (overlap / smallest) >= 0.5:
                found = True
                break
        
        if not found:
            fn_details.append({
                "value": val, "text": text, "cleaned": cleaned,
                "start": s, "end": e, "log": log
            })

print(f"\nTotal FNs: {len(fn_details)}")

# For each FN, understand exactly why the pattern fails
for i, fn in enumerate(fn_details):
    v = fn["value"]
    t = fn["text"]
    c = fn["cleaned"]
    s, e = fn["start"], fn["end"]
    log = fn["log"]
    
    print(f"\n{'='*70}")
    print(f"FN #{i+1}: value={repr(v)}")
    print(f"  text: {repr(t)}")
    
    # Show cleaned text around entity
    clean_before = c[max(0,s-10):s]
    clean_span = c[s:e]
    clean_after = c[e:e+50]
    print(f"  cleaned: '{clean_before}|{clean_span}|{clean_after}'")
    print(f"  deobf_log: {log}")
    
    # All pattern matches in cleaned text
    matches = list(current_pattern.finditer(c))
    print(f"  pattern matches in cleaned text ({len(matches)}):")
    for m in matches:
        print(f"    [{m.start()}:{m.end()}] '{m.group()}'")
    
    # Test improved patterns
    test_patterns = [
        ("current", r'\b[\w.+*-]+@[\w-]+\.[\w.-]+\b'),
        ("v2_no_star_limit", r'\b[\w.+\-*%]+@[\w\-]+(?:\.[\w\-]+)+\b'),
        ("v3_require_dot_in_domain", r'\b[\w.+\-*%]+@[\w\-]+(?:\.[\w\-]+){1,}\b'),
        ("v4_longer_tld", r'\b[\w.+\-*%]+@[\w\-]+(?:\.[\w\-]+)+\b'),
        ("v5_loose_boundary", r'(?:^|\s|[<(\\[\'"]|(?<=\u200B))[\w.+\-*%]+@[\w\-]+(?:\.[\w\-]+)+(?=[\s>)\],.;:!?\'"\\]|$|[\u200B\u200C\u200D\uFEFF])'),
        ("v6_anchor_robust", r'(?<![^\s([<\'"])\s*[\w.+\-*%]+@[\w\-]+(?:\.[\w\-]+)+'),
        ("v7_simple_improved", r'\b[\w.+\-*%]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+\b'),
    ]
    
    for name, pat in test_patterns:
        try:
            tr = re.compile(pat, re.UNICODE)
            # Test on cleaned text
            m = tr.search(c)
            if m:
                # Check if it overlaps with entity
                ms, me = m.start(), m.end()
                overlap = min(e, me) - max(s, ms)
                smallest = min(e - s, me - ms)
                covers = smallest > 0 and (overlap / smallest) >= 0.5
                print(f"  {name}: '{m.group()}' at [{ms}:{me}] {'✓ CATCHES' if covers else '✗ misses span'}")
            else:
                print(f"  {name}: no match")
        except Exception as ex:
            print(f"  {name}: ERROR {ex}")