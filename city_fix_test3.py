#!/usr/bin/env python3
"""Test further refined city patterns with FP guards."""
import re

# Pattern A: City before state/postcode
# Must be preceded by comma (standard address: ", City, STATE/ZIP")
# OR start of string / beginning of segment (e.g., "Visit New York, NY")
# Use lookbehind: either comma+space OR start-of-word-boundary
pat_a = r"(?:(?<=\,\s)|(?<=^))[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:[A-Z]{2}\s+\d{5}|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}|[A-Za-z]+\s+\d{3,5}))"

# Better: just use a lookbehind for start/after-comma
pat_a2 = r"(?:(?<=\,\s)|(?<=^))[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:[A-Z]{2}(?:\s+\d{5})?|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}))"
# Wait that's too loose - "NY" alone could match many things

# Best approach: match cities in address position 
# "..., City, ST ZIP" or "..., City, POSTCODE"
pat_a3 = r"(?:(?<=\,\s)|(?<=^))[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:(?:[A-Z]{2}\s+\d{5}(?:-\d{4})?|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2})))"

# Also need to add "City is/has/was" pattern for standalone common-city naming
# But that has high FP risk. Let me be more conservative.

# Pattern B: Major / capital city at start of sentence (before "has", "is", "was")
# Only the most well-known cities to minimize FPs
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Delhi|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Seoul|Bangkok|Jakarta|Hanoi|Dubai|Istanbul|Cairo|Jerusalem|Riyadh|Singapore|Manila)(?=\s+(?:has|is|was|lies|sits|became|remains|serves|boasts|encompasses|covers|spans|welcomes|hosts|attracts))"

# Let me test with the FN examples plus some FP edge cases
texts = [
    # FN cases
    ("FN1", "Our office is at 350 Fifth Avenue, New York, NY 10118"),
    ("FN2", "Paris has a population of over 2 million people and is the capital of France."),
    ("FN3", "Visit us at 10 Downing Street, London, SW1A 2AA"),
    # Edge cases - should MATCH correctly
    ("OK1", "Berlin is the capital of Germany"),
    ("OK2", "Visit New York, NY 10001 for the conference"),
    ("OK3", "Tokyo has hosted the Olympics multiple times."),
    ("OK4", "located in London, SW1A 1AA at the Houses of Parliament"),
    # Edge cases - should NOT match (FP guards)
    ("FP1", "The Paris office is located at 123 Rue de Rivoli"),  # "The Paris" not "Paris has/is"
    ("FP2", "London is not the capital"),  # "London is" matches... but is this OK? It IS a city.
    ("FP3", "Spring has arrived early this year"),  # "Spring" capitalized before "has" 
    ("FP4", "Summer is my favorite season"),
    ("FP5", "Berlin has a great subway system"),  # This IS correct - Berlin is a city
    ("FP6", "James has been working at Microsoft"),
    ("FP7", "Paris is known for..."),  # This is correct
]

for label, text in texts:
    print(f"\n--- {label}: '{text}' ---")
    for name, pat, conf in [("A3", pat_a3, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")