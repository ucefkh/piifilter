#!/usr/bin/env python3
"""Analyze specific failing examples."""
import json
import re
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType

data = json.load(open('benchmarks/data/pii_dataset.json'))

# Look at a few key examples
for idx in [54, 73, 19, 45, 104, 94]:
    ex = data['examples'][idx]
    text = ex['text']
    print(f"\n=== Ex {idx} ===")
    print(f"Text: {repr(text[:120])}")
    for e in ex['entities']:
        substr = text[e['start']:e['end']]
        print(f"  Expected: {e['type']}={repr(e['value'])} at [{e['start']}:{e['end']}] (substr={repr(substr)})")

# Check GPS pattern 2 against Ex 54
gps_pat2 = r"[-+]?\d{1,2}\.\d{4,}\s*[,;]\s*[-+]?\d{1,3}\.\d{4,}"
text54 = data['examples'][54]['text']
print(f"\n\n=== GPS pattern on Ex 54 ===")
pat = re.compile(gps_pat2)
for m in pat.finditer(text54):
    print(f"  Matches: {repr(m.group())} at [{m.start()}:{m.end()}]")

# Check Lat: pattern
lat_pat = r"(?i)\b(?:lat|lng|lon|latitude|longitude|coordinates?|coords?|gps)\s*[:=]?\s*[-+]?\d{1,3}\.\d+(?:\s*°)?"
pat2 = re.compile(lat_pat)
print(f"\n=== Lat/Lng patterns on Ex 54 ===")
for m in pat2.finditer(text54):
    print(f"  Matches: {repr(m.group())} at [{m.start()}:{m.end()}]")