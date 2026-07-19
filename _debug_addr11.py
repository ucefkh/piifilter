"""Test negative lookbehind for 'is ' before address."""
import re

# Current pattern line 170 with negative lookbehind for "is "
pat = re.compile(r"\b(?<!is\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")

# Wait, the lookbehind position must be at the boundary where the number starts
# \b\d{1,5} — the \b is at the position before the digit
# But we want to check what's at \b, which is before the number
# \b ensures there's a word boundary before the number
# We want: (?<!is )\b\d — so if there's "is " before the word boundary, skip

# Actually, the issue is that \b matches at a word boundary. If we have "is 123",
# \b is between " " and "1 2 3". We want to check: is the previous 3 chars "is "?
# \b(?<!is )\d — \b is zero-width at the boundary, then lookbehind 3 chars, then digit
# But (?<!is ) at the \b position means we look BACK 3 chars from the word boundary position.
# The chars before "123" are "is " so it's blocked. Good.

pat2 = re.compile(r"\b(?<!is\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")

tests = [
    ("Our office is at 350 Fifth Avenue, New York, NY 10118", True), # should match: "at " before, not "is "
    ("Visit us at 10 Downing Street, London, SW1A 2AA", True),
    ("Home address: 123 Maple Drive, Springfield, IL 62704", True),
    ("My street is 123 Main Street, not 123 Main St.", False), # should NOT match: "is " before
    ("The address is at 42 Wallaby Way, Sydney", True), # should match: "at " before
    ("Contact us: 456 Oak Avenue", True), # should match: keyword "Contact"
    ("The address is 789 Pine Road", True), # "is " before but "address" before that — HMM
]

for text, should_match in tests:
    m = pat2.search(text)
    matched = bool(m)
    status = "✓" if matched == should_match else "✗"
    print(f'{status} {"Matched" if matched else "No"} for: {text[:60]}... ({matched} vs expected {should_match})')
    if m:
        print(f'     Match: "{m.group()}" at {m.start()}-{m.end()}')