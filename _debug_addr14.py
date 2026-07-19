import re

# New keyword-prefixed address with additional negative lookahead for pop culture refs
keywords = [
    r"at\s+",
    r"address:\s*",
    r"address\s+",
    r"is\s+at\s+",
    r"office\s+is\s+at\s+",
    r"Home\s+address:\s+",
    r"home\s+address:\s+",
    r"Visit\s+us\s+at\s+",
    r"HQ\s+is\s+at\s+",
    r"mailing\s+address:\s+",
]
kw_group = "|".join(keywords)
new_pat = re.compile(
    r"(?:" + kw_group + r")"
    r"(\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway))"
    r"(?!\s*\([^)]*(?:famous|from\s+[A-Z]))"
    r"\b"
)

tests = [
    "Our office is at 350 Fifth Avenue, New York, NY 10118",
    "Visit us at 10 Downing Street, London, SW1A 2AA",
    "Home address: 123 Maple Drive, Springfield, IL 62704",
    "My street is 123 Main Street, not 123 Main St.",
    "The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)",
    "the address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)",
]

for t in tests:
    m = new_pat.search(t)
    print(f'{"✓" if m else "✗"} {"Matched" if m else "No"} for: {t[:60]}')
    if m:
        print(f'     "{m.group()}"')