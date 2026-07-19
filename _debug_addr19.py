import re

# Positive lookahead for pop culture context
# After the street suffix, skip some words, then check for (famous|from movie|from show)
text = "42 Wallaby Way, Sydney (famous from Finding Nemo)"

# Test with a more flexible negative lookahead
pat = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

for m in pat.finditer(text):
    print(f'Match: "{m.group()}" at {m.start()}-{m.end()}')

# Test with the full keyword version
pat2 = re.compile(r"(?:address:\s*|at\s+|is\s+at\s+|office\s+is\s+at\s+|Home\s+address:\s+|home\s+address:\s+|Visit\s+us\s+at\s+|HQ\s+is\s+at\s+)(\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway))(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

tests = [
    "Our office is at 350 Fifth Avenue, New York, NY 10118",
    "Visit us at 10 Downing Street, London, SW1A 2AA",
    "Home address: 123 Maple Drive, Springfield, IL 62704",
    "My street is 123 Main Street, not 123 Main St.",
    "The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)",
    "the address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)",
]

for t in tests:
    m = pat2.search(t)
    print(f'{"✓" if m else "✗"} {"Matched" if m else "No"} for: {t[:60]}')
    if m:
        print(f'     "{m.group()}"')