#!/usr/bin/env python3
"""Check surrounding context for the 3 FN cases."""
import re

# Example 1: "Our office is at 350 Fifth Avenue, New York, NY 10118"
# "New York" [35:43] is preceded by ", " and followed by ", NY 10118"
# NY is a US state abbreviation

# Example 2: "Paris has a population of over 2 million people and is the capital of France."
# "Paris" [0:5] is at position 0, followed by " has"

# Example 3: "Visit us at 10 Downing Street, London, SW1A 2AA"
# "London" [31:37] is preceded by ", " and followed by ", SW1A 2AA" (UK postcode)

# Proposed patterns:
patterns_to_add = []

# Pattern A: City in address position — city followed by state abbreviation or postcode
# Matches: "New York, NY 10118" -> just "New York", "London, SW1A 2AA" -> just "London"
# Use positive lookahead for ", STATE" or ", POSTCODE"
pat_a = r"\b[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:[A-Z]{2}\s+\d{5}|[A-Za-z0-9]+\s+[A-Za-z0-9]{2,}))"
# This matches "New York" before ", NY 10118" or "London" before ", SW1A 2AA"

# Pattern B: Capital city at start of sentence (common knowledge / major cities)
# Only match well-known capital/major cities followed by verb context
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Singapore|Hong Kong)(?=\s+(?:has|is|was|lies|sits|stands|became|remains|serves|boasts|offers|features|encompasses|covers|spans))"

print(f"Pattern A: {pat_a}")
print(f"Pattern B: {pat_b}")

# Test patterns
texts = [
    "Our office is at 350 Fifth Avenue, New York, NY 10118",
    "Paris has a population of over 2 million people and is the capital of France.",
    "Visit us at 10 Downing Street, London, SW1A 2AA",
]

for text in texts:
    print(f"\n--- '{text}' ---")
    for name, pat, conf in [("A", pat_a, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")