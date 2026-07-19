#!/usr/bin/env python3
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

# Check the PERSON pattern
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'PERSON' and 'my name' in raw_pattern:
        print(f'PERSON pattern: {repr(raw_pattern)}')

# Also test directly
import re
text = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com Phone: +1-555-123-4567"
pat = re.compile(r"(?:\bmy name is|\bI.m |\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")
m = pat.search(text)
if m:
    print(f'Match: "{m.group()}" at [{m.start()}:{m.end()}]')
else:
    print('No match')
    # test sub-patterns
    for sub in ['I.m ', 'I.m']:
        sub_pat = re.compile(r'\b' + sub)
        m2 = sub_pat.search(text)
        if m2:
            print(f'  sub "{sub}" matches: "{m2.group()}" at [{m2.start()}:{m2.end()}]')
        else:
            print(f'  sub "{sub}" NO match')