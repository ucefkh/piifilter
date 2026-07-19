#!/usr/bin/env python3
"""Test all the new patterns with (?-i:[A-Z]) syntax."""
import re

tests = [
    ("PERSON I'm", r"(?i)(?:\bmy name is|\bI'm|\bcall me|\bname is)\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+){0,2}\b",
     "Hi, I'm Alice Johnson from Acme Corp.", "I'm Alice Johnson"),
    ("CEO", r"(?i)\b(?:ceo|cfo|cto|president|director|founder|owner)\s+(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b",
     "Our CEO Bob Smith (bob@company.com) approved the merger.", "CEO Bob Smith"),
    ("Contact", r"(?i)\bContact\s+(?:person|name):\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b",
     "Contact person: Donna Noble (donna@temp-services.co.uk).", "Contact person: Donna Noble"),
    ("Person:", r"(?i)\bPerson:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)*\b",
     "Person: Dr. Sarah Chen works at Microsoft Research in Redmond", "Person: Dr. Sarah Chen"),
    ("Customer", r"(?i)\b(?:customer|client)\s+(?:name\s+)?(?:is\s+)?(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b",
     "Our customer Jane Smith from Widgets Inc.", "customer Jane Smith"),
    ("Customer:", r"(?i)\bCustomer:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b",
     "Customer: Martha Jones (martha.jones@bigpharma.com)", "Customer: Martha Jones"),
    ("Employee", r"(?i)\b(?:employee|staff|teammate|colleague|manager|supervisor|engineer|developer|designer)\s+(?:name\s+)?(?:is\s+)?(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b",
     "Employee Bob Marley from accounting", "Employee Bob Marley"),
    ("Employee:", r"(?i)\bEmployee:\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b",
     "Employee: Rose Tyler (rose@torchwood.xyz)", "Employee: Rose Tyler"),
]

for name, pat_str, text, expected in tests:
    pat = re.compile(pat_str)
    m = pat.search(text)
    if m:
        matched = m.group()
        status = "OK" if expected in matched else "MISMATCH"
        print(f'  {name}: {status} — got "{matched}", expected contains "{expected}"')
    else:
        print(f'  {name}: FAIL — no match')