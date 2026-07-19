import re
# Test variable-length lookbehind in Python re
pat = re.compile(r'(?<=(?:address\s*:\s*|at\s+|is\s+at\s+))\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b')
tests = [
    "Our office is at 350 Fifth Avenue, New York, NY 10118",
    "Visit us at 10 Downing Street, London, SW1A 2AA",
    "Home address: 123 Maple Drive, Springfield, IL 62704",
    "My street is 123 Main Street, not 123 Main St.",
    "The address is at 42 Wallaby Way, Sydney",
]
for t in tests:
    m = pat.search(t)
    print(f'{t[:50]:50s} → match: {bool(m)}', end='')
    if m:
        print(f' "{m.group()}"', end='')
    print()