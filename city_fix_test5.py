#!/usr/bin/env python3
"""Refined address-city pattern with better FP protection."""
import re

# Pattern A: City before US state abbreviation + optional ZIP
# Only match KNOWN state abbreviations after comma (2-letter uppercase)
# This is much more precise than matching any 2-letter code
states = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
# The city name itself must not contain known street/location suffixes
pat_a = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?=\s*,\s*(?:" + states + r")(?:\s+\d{5}(?:-\d{4})?)?\b)"

# Pattern A2: City before UK postcode (format: A1 1AA, SW1A 1AA, etc.)
pat_a2 = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?(?=\s*,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b)"

# Pattern B: Major capital cities at start of sentence followed by known verb
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Delhi|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Seoul|Bangkok|Jakarta|Hanoi|Dubai|Istanbul|Cairo|Jerusalem|Riyadh|Singapore|Manila|Kuala Lumpur)(?=\s+(?:has|is|was|lies|sits|became|remains|serves|boasts|encompasses|covers|spans|welcomes|hosts|attracts))"

texts = [
    ("FN1", "Our office is at 350 Fifth Avenue, New York, NY 10118"),
    ("FN2", "Paris has a population of over 2 million people and is the capital of France."),
    ("FN3", "Visit us at 10 Downing Street, London, SW1A 2AA"),
    ("OK2", "Visit New York, NY 10001 for the conference"),
    ("OK4", "located in London, SW1A 1AA at the Houses of Parliament"),
    ("OK5", "Berlin is the capital of Germany"),
    ("OK6", "Tokyo has hosted the Olympics multiple times."),
    ("FP1", "The Paris office is located at 123 Rue de Rivoli"),
    ("FP2", "London is not the capital"),
    ("FP3", "Spring has arrived early this year"),
    ("FP4", "Summer is my favorite season"),
    ("FP5", "Berlin has a great subway system"),
    ("FP6", "James has been working at Microsoft"),
    ("FP7", "Paris is known for..."),
    ("FP8", "Fifth Avenue, NY 10001 is a famous street"),  # "Fifth Avenue" should NOT match
    ("FP9", "The Study has been completed."),
    ("FP10", "Support has been great."),
    ("FP11", "Office, NY 10001"),  # Should not match
    ("FP12", "Let me check London, OH 43140"),  # London OH is a real place! This TP actually
    ("FP13", "Berlin, NJ 08009"),  # Real town too
    # Check no FP on known non-city words
    ("FP14", "Configuration has been updated"),
    ("FP15", "System has been restarted"),
    ("FP16", "Dashboard has been loaded"),
]

for label, text in texts:
    print(f"\n--- {label}: '{text}' ---")
    for name, pat, conf in [("A1", pat_a, 0.55), ("A2", pat_a2, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")