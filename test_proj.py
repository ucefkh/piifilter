#!/usr/bin/env python3
import re

# Current patterns
current = [
    (0.80, r"(?i)\b(?:project|initiative|campaign|program)\s*:\s*(?:(?:name\s*)?(?:is\s*)?(?:called\s*)?)?(?-i:[A-Z])[a-zA-Z0-9]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)*\b"),
    (0.85, r"\b(?:Project|Operation|Initiative|Program|Code[- ]?name)\s+(?-i:[A-Z])[a-zA-Z0-9]+\b"),
    (0.80, r"\b(?:Project|Operation|Initiative|Program|Task)(?:\s+code[- ]?name)?\s+(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)?\b"),
    (0.70, r"(?i)\b(?:working\s+on|assigned\s+to)\s+(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z]+)?\b"),
    (0.70, r"(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\s+milestone\s+due\b"),
    (0.65, r"(?i)(?-i:[A-Z])[a-zA-Z]+(?:\s+(?-i:[A-Z])[a-zA-Z]+)?\s+is\s+in\s+(?:development|maintenance|maint)\b"),
]

# Proposed new pattern: lowercase project/initiative + capitalized name (no colon needed)
# "for the project Vulcan", "project Galactic", "- project Pandorica", "for project Last Centurion"
# Captures from "project/initiative" keyword through the name(s)
new_pattern = r"(?i)\b(?:project|initiative|campaign|program)\s+(?:(?:the|our|this|that|a|an)\s+)?(?-i:[A-Z])[a-zA-Z0-9]+(?:\s+(?-i:[A-Z])[a-zA-Z0-9]+)*\b"

tests = [
    "for the project Vulcan.",
    "for project Galactic.",
    "- project Pandorica",
    "for project Last Centurion",
    "- project Impossible Astronaut",
    "Project: Project Phoenix is our codename",
    "Project Nebula starts Q1 and Project Orion is in maintenance mode.",
    "Project Bad Wolf is GO.",
]

print("=== Current patterns ===")
for text in tests:
    matches = set()
    for score, pat in current:
        for m in re.finditer(pat, text):
            matches.add((m.group(), m.start(), m.end()))
    if matches:
        for g, s, e in sorted(matches):
            print(f"  {text!r} -> {g!r} at {s}-{e}")
    else:
        print(f"  {text!r} -> NO MATCH")

print("\n=== New pattern ===")
for text in tests:
    for m in re.finditer(new_pattern, text):
        print(f"  {text!r} -> {m.group()!r} at {m.start()}-{m.end()}")
    else:
        if not re.findall(new_pattern, text):
            print(f"  {text!r} -> NO MATCH")