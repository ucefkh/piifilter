#!/usr/bin/env python3
import re

# Current pattern
pat = re.compile(r'(?:\bmy name is|\bI\'?m |\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', re.IGNORECASE)
print("Current pattern test:")
for text in ["I'm Alice Johnson", "Hi, I'm Alice Johnson from Acme Corp"]:
    m = pat.search(text)
    if m:
        print(f'  "{text}" -> "{m.group()}" at [{m.start()}:{m.end()}]')
    else:
        print(f'  "{text}" -> FAIL')

# Fix: remove the trailing space in I'm 
pat2 = re.compile(r'(?:\bmy name is|\bI.m|\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', re.IGNORECASE)
print("\nPattern with no space in I'm:")
for text in ["I'm Alice Johnson", "Hi, I'm Alice Johnson from Acme Corp"]:
    m = pat2.search(text)
    if m:
        print(f'  "{text}" -> "{m.group()}" at [{m.start()}:{m.end()}]')
    else:
        print(f'  "{text}" -> FAIL')

# Also try with non-optional '
pat3 = re.compile(r'(?:\bmy name is|\bI.m |\bcall me|\bname is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', re.IGNORECASE)
print("\nPattern with space after I'm:")
for text in ["I'm Alice Johnson", "Hi, I'm Alice Johnson from Acme Corp"]:
    m = pat3.search(text)
    if m:
        print(f'  "{text}" -> "{m.group()}" at [{m.start()}:{m.end()}]')
    else:
        print(f'  "{text}" -> FAIL')

# Try a completely different approach: just capture capitalized words after known context
pat4 = re.compile(r"(?i)\b(?:my name is|I'm |call me|name is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")
print("\nSimpler pattern:")
for text in ["I'm Alice Johnson", "Hi, I'm Alice Johnson from Acme Corp"]:
    m = pat4.search(text)
    if m:
        print(f'  "{text}" -> "{m.group()}" at [{m.start()}:{m.end()}]')
    else:
        print(f'  "{text}" -> FAIL')