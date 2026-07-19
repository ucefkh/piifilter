#!/usr/bin/env python3
import re

patterns = [
    (r'\b[A-Z][a-z]+\s+(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|Incorporated|PLC|AG|SA|BV|NV)\.?\b', 'single word + suffix'),
    (r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+(?:Inc|Corp|LLC|Ltd|Limited|GmbH|Co|Company|Corporation|PLC|AG|SA|BV|NV)\.?\b', 'multi word + suffix'),
]
text = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com"
for pat_str, name in patterns:
    pat = re.compile(pat_str)
    for m in pat.finditer(text):
        print(f'  {name}: "{m.group()}" at [{m.start()}:{m.end()}]')

print()
print('=== PERSON test ===')
text2 = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com Phone: +1-555-123-4567"
person_pat = re.compile(r'(?:\bmy name is|\bI\'?m |\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b')
for m in person_pat.finditer(text2):
    print(f'  PERSON: "{m.group()}" at [{m.start()}:{m.end()}]')
if not person_pat.search(text2):
    print('  No PERSON match')
    pat2 = re.compile(r'(?:\bmy name is|\bI\'?m |\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', re.IGNORECASE)
    for m in pat2.finditer(text2):
        print(f'  PERSON (re.I): "{m.group()}" at [{m.start()}:{m.end()}]')
    if not pat2.search(text2):
        print('  No match even with IGNORECASE')
        # The issue might be escaping
        pat3 = re.compile(r'(?:\bmy name is|\bI.m |\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', re.IGNORECASE)
        for m in pat3.finditer(text2):
            print(f'  PERSON (re.I, dot): "{m.group()}" at [{m.start()}:{m.end()}]')

# Test phone patterns
print()
print('=== PHONE test ===')
phone_texts = [
    "+966 55 123 4567",
    "+7 495 123-45-67",
    "+972 50 123 4567",
    "(415) 555-2671",
]
for pt in phone_texts:
    pat = re.compile(r"(?:^|\s)\+\d{1,3}\s+\d{2,3}\s+\d{3}\s+\d{3,4}\b")
    m = pat.search(pt)
    print(f'  Phone "{pt}": ', end='')
    if m:
        print(f'MATCH "{m.group()}" at [{m.start()}:{m.end()}]')
    else:
        print('NO MATCH for pattern 2')
        pat2 = re.compile(r"(?:^|\s)\+\d{1,3}[-.\s]\d{2,4}[-.\s]\d{3,4}[-.\s]\d{4}\b")
        m2 = pat2.search(pt)
        if m2:
            print(f'    But pattern 1 matches: "{m2.group()}"')
        else:
            print('    Neither matches')
            # Debug
            pat3 = re.compile(r'(?:^|\s)\+')
            m3 = pat3.search(pt)
            if m3:
                print(f'    + found at {m3.start()}={m3.end()}')