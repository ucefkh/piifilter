#!/usr/bin/env python3
"""Test that new patterns work with IGNORECASE."""
import re

# The PERSON pattern with (?i) and (?=[A-Z]) lookahead
text = "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com"

# Test 1: with (?i) and (?=[A-Z])
pat1 = re.compile(r"(?i)(?:\bmy name is|\bI.m|\bcall me|\bname is)\s+(?=[A-Z])[A-Z][a-z]+(?:\s+(?=[A-Z])[A-Z][a-z]+){0,2}\b")
print("Test 1: With (?i) + (?=[A-Z]):")
for m in pat1.finditer(text):
    print(f'  "{m.group()}" at [{m.start()}:{m.end()}]')

# Test 2: without any flags
pat2 = re.compile(r"(?:\bmy name is|\bI.m|\bcall me|\bname is)\s+(?=[A-Z])[A-Z][a-z]+(?:\s+(?=[A-Z])[A-Z][a-z]+){0,2}\b")
print("Test 2: Without flags:")
for m in pat2.finditer(text):
    print(f'  "{m.group()}" at [{m.start()}:{m.end()}]')

# Test 3: CEO pattern
text2 = "Our CEO Bob Smith (bob@company.com) approved the merger."
pat3 = re.compile(r"\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?=[A-Z])[A-Z][a-z]+(?:\s+(?=[A-Z])[A-Z][a-z]+)?\b")
print(f"\nTest CEO on '{text2}':")
for m in pat3.finditer(text2):
    print(f'  "{m.group()}" at [{m.start()}:{m.end()}]')

pat3i = re.compile(r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?=[A-Z])[A-Z][a-z]+(?:\s+(?=[A-Z])[A-Z][a-z]+)?\b")
print("Test CEO with (?i):")
for m in pat3i.finditer(text2):
    print(f'  "{m.group()}" at [{m.start()}:{m.end()}]')

# Test 4: Contact person
text3 = "Contact person: Donna Noble (donna@temp-services.co.uk)."
pat4 = re.compile(r"(?i)\bContact\s+(?:person|name):\s*(?=[A-Z])[A-Z][a-z]+(?:\s+(?=[A-Z])[A-Z][a-z]+)?\b")
for m in pat4.finditer(text3):
    print(f'\nTest Contact: "{m.group()}" at [{m.start()}:{m.end()}]')