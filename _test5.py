#!/usr/bin/env python3
"""Debug PERSON pattern matching."""
import re
import sys
sys.path.insert(0, 'plugins/detector-regex/src')

text = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com Phone: +1-555-123-4567"

# Read the actual pattern from the module
from piifilter_detector_regex.patterns import PATTERN_DEFS
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'PERSON' and 'my name' in raw_pattern:
        print(f'Pattern repr: {repr(raw_pattern)}')
        print(f'Pattern: {raw_pattern}')
        pat = re.compile(raw_pattern)
        m = pat.search(text)
        if m:
            print(f'Match: "{m.group()}" at [{m.start()}:{m.end()}]')
        else:
            print('No match')

# Now test each subpattern separately
pats = [
    r"\bmy name is\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
    r"\bI.m\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
    r"\bcall me\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
    r"\bname is\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",
]
print("\n=== Sub-pattern tests ===")
for p in pats:
    pat = re.compile(p)
    m = pat.search(text)
    if m:
        print(f'  MATCH: "{m.group()}" at [{m.start()}:{m.end()}] for pattern: {p}')
    else:
        print(f'  FAIL for: {p}')

# Test I.m specifically
pat = re.compile(r"\bI.m\s+[A-Z][a-z]+")
m = pat.search(text)
print(f"\nDirect I.m test: {m.group() if m else 'FAIL'} at [{m.start()}:{m.end()}]" if m else "\nDirect I.m test: FAIL")