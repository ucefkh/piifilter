import re

# Try: block parentheticals that contain movie/show/film/game/TV-type words
# after a capitalized word (e.g., "Finding Nemo", "Toy Story")
# This is more general: checks for (X (from|in|of) ... Movie|Show|Film|Book etc.)
# OR (X Movie|Show|Film|Book etc.)

# Version: address followed by comma+city+ (media reference)
# Pattern: [,.]?\s*(\w+\s+){0,5}\([^)]*(?:movie|show|film|game|series|cartoon|animation|TV|episode)

# Actually, the most principled approach: 
# A real address doesn't have a parenthetical annotation identifying it as fictional.
# A fictional/anecdotal address often has a pop-culture citation.
# The pattern is: parenthetical with "from + CapitalizedWord" OR "famous" OR containing (movie|show|film)

# Let me try matching "from " anywhere in the paren (not just after specific words)
# Combined with checking if the paren contains known media indicators

# Simple: block if paren has "from \s+ [A-Z]" AND also has a media indicator word
# OR if paren has "famous"
# This avoids the specific "Finding Nemo" hardcoding

# Actually simplest: block on any parenthetical containing both a capitalized 
# word and at least one of {movie, show, film, game, series, cartoon, animation, episode}
# This is linguistically general but still targeted

pat = re.compile(r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:movie|show|film|game|series|cartoon|animation|episode|from\s+[A-Z]))\b")

tests = [
    ("Our office is at 350 Fifth Avenue, New York, NY 10118", True),
    ("Visit us at 10 Downing Street, London, SW1A 2AA", True),
    ("Home address: 123 Maple Drive, Springfield, IL 62704", True),
    ("My street is 123 Main Street, not 123 Main St.", False),
    ("The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)", False),
    ("42 Wallaby Way, Sydney (from the movie Finding Nemo)", False),
    ("42 Wallaby Way, Sydney (as seen in Toy Story)", True),  # No "from" or movie word in paren? Wait, Toy Story has uppercase
    # Actually "(from the movie Finding Nemo)" — "from " + "the " + "movie" → "the" is lowercase, "movie" is lowercase -> `from\s+[A-Z]` doesn't match at "from the"
    # But `movie` should match!
    ("Visit us at 10 Downing Street, London SW1A (near Parliament)", True),  # Should still match
    ("The office is at 123 Maple Drive, Apt 4B", True),
    ("Located at 1600 Pennsylvania Avenue NW, Washington DC", True),
    # New test: paren without media context, should match
    ("Our office is at 100 Main Street, Floor 3 (reception)", True),
]

for t, expected in tests:
    m = pat.search(t)
    matched = bool(m)
    ok = "✓" if matched == expected else "✗"
    print(f'{ok} matched={matched} expected={expected}: {t[:75]}')
    if m:
        print(f'     "{m.group()}"')