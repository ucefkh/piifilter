import re

pat = re.compile(r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:from\s+[A-Z][a-zA-Z]*))\b")

tests = [
    ("Our office is at 350 Fifth Avenue, New York, NY 10118", True),
    ("Visit us at 10 Downing Street, London, SW1A 2AA", True),
    ("Home address: 123 Maple Drive, Springfield, IL 62704", True),
    ("My street is 123 Main Street, not 123 Main St.", False),
    ("The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)", False),
    ("42 Wallaby Way, Sydney (from the movie Finding Nemo)", False),
    ("42 Wallaby Way, Sydney (as seen in Finding Nemo)", True),  # This one still matches because "from Finding" is NOT in the parens
    ("Visit us at 10 Downing Street, London SW1A (near Parliament)", True),  # Parenthetical with location info, should match
    ("The office is at 123 Maple Drive, Apt 4B", True),  # Apartment info in parens, should match
]

for t, expected in tests:
    m = pat.search(t)
    matched = bool(m)
    ok = "✓" if matched == expected else "✗"
    print(f'{ok} matched={matched} expected={expected}: {t[:70]}')
    if m:
        print(f'     "{m.group()}"')