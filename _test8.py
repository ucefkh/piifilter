#!/usr/bin/env python3
"""Debug the (?![a-z]) under (?i)."""
import re

text = "Hi, I'm Alice Johnson from Acme Corp."

# The key question: what does the alternation do with (?i)?
pat = re.compile(r'(?i)(?:\bmy name is|\bI.m|\bcall me|\bname is)\s+(?![a-z])[A-Z][a-z]+')
m = pat.search(text)
print(f'Full pattern: {m.group() if m else "NO MATCH"}')
if m:
    print(f'  At [{m.start()}:{m.end()}]')
    # Show what comes after the match
    print(f'  After match: {repr(text[m.end():m.end()+20])}')

# Try with just I.m
pat2 = re.compile(r'(?i)\bI.m\s+(?![a-z])[A-Z][a-z]+')
m2 = pat2.search(text)
print(f'\nSimplified: {m2.group() if m2 else "NO MATCH"}')
if m2:
    print(f'  At [{m2.start()}:{m2.end()}]')

# Try without (?![a-z])
pat3 = re.compile(r'(?i)\bI.m\s+[A-Z][a-z]+')
m3 = pat3.search(text)
print(f'\nWithout lookahead: {m3.group() if m3 else "NO MATCH"}')
if m3:
    print(f'  At [{m3.start()}:{m3.end()}]')