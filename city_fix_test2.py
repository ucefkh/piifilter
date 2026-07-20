#!/usr/bin/env python3
"""Test refined city patterns."""
import re

# Refined Pattern A: City before state/postcode — must be preceded by comma
# "..., New York, NY 10118" or "..., London, SW1A 2AA"
# Use lookbehind for comma+space before the city name
pat_a = r"(?<=\,\s)[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?(?=\s*,\s*(?:[A-Z]{2}\s+\d{5}|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}|[A-Za-z]+\s+\d{3,5}))"

# Pattern B: major city at start of sentence
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Singapore|Hong Kong|Seoul|Bangkok|Jakarta|Manila|Hanoi|Kuala Lumpur|Dubai|Istanbul|Cairo|Jerusalem|Riyadh|Abu Dhabi|Santiago|Buenos Aires|Lima|Bogota|Mexico City|Rio de Janeiro|Sao Paulo|Sydney|Melbourne|Auckland|Wellington|Cape Town|Nairobi|Lagos|Casablanca|Algiers|Tripoli|Damascus|Baghdad|Tehran|Kabul|Islamabad|New Delhi|Mumbai|Kolkata|Chennai|Bangalore|Hyderabad)(?=\s+(?:has|is|was|were|lies|sits|stands|became|remains|serves|boasts|offers|features|encompasses|covers|spans|takes|covers|attracts|draws|welcomes|hosts|contains|includes|comprises))"

# Pattern C: Better ["based in", "located in"] — should also match "office is in City"  
# Currently pattern[174] "based in/located in" captures the prefix. But we also need
# patterns that match just the city after phrases like "office is at/in..."
# Actually "office is at..." doesn't indicate a city context unless address follows.
# Let me focus on the two above.

print(f"Pattern A: {pat_a}")
print(f"\nPattern B: {pat_b}")

texts = [
    "Our office is at 350 Fifth Avenue, New York, NY 10118",
    "Paris has a population of over 2 million people and is the capital of France.",
    "Visit us at 10 Downing Street, London, SW1A 2AA",
    # Edge cases to check
    "The Paris office is located at 123 Rue de Rivoli",
    "Berlin is the capital of Germany",
    "Visit New York, NY 10001 for the conference",
    "Located in Paris, France - the headquarters is at...",
    "I live in London, England near the Thames",
]

for text in texts:
    print(f"\n--- '{text}' ---")
    for name, pat, conf in [("A", pat_a, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")