#!/usr/bin/env python3
"""Test (?![a-z]) lookahead to enforce uppercase under IGNORECASE."""
import re

text = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com"

# Test with (?i) and (?![a-z])
pat1 = re.compile(r"(?i)(?:\bmy name is|\bI.m|\bcall me|\bname is)\s+(?![a-z])[A-Z][a-z]+(?:\s+(?![a-z])[A-Z][a-z]+){0,2}\b")
print("Test (?i) + (?![a-z]):")
for m in pat1.finditer(text):
    print(f'  "{m.group()}" at [{m.start()}:{m.end()}]')

# CEO pattern
text2 = "Our CEO Bob Smith (bob@company.com) approved the merger."
pat2 = re.compile(r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?![a-z])[A-Z][a-z]+(?:\s+(?![a-z])[A-Z][a-z]+)?\b")
print(f"\nCEO pattern on '{text2}':")
for m in pat2.finditer(text2):
    print(f'  "{m.group()}" at [{m.start()}:{m.end()}]')

# Person:
text3 = "Person: Dr. Sarah Chen works at Microsoft Research in Redmond"
pat3 = re.compile(r"(?i)\bPerson:\s*(?![a-z])[A-Z][a-z]+(?:\s+(?![a-z])[A-Z][a-z]+)*\b")
for m in pat3.finditer(text3):
    print(f"\nPerson: -> '{m.group()}' at [{m.start()}:{m.end()}]")

# Contact person
text4 = "Contact person: Donna Noble (donna@temp-services.co.uk)."
pat4 = re.compile(r"(?i)\bContact\s+(?:person|name):\s*(?![a-z])[A-Z][a-z]+(?:\s+(?![a-z])[A-Z][a-z]+)?\b")
for m in pat4.finditer(text4):
    print(f"\nContact: '{m.group()}' at [{m.start()}:{m.end()}]")