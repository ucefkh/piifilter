import re

# Test just the negative lookahead
text = "42 Wallaby Way, Sydney (famous from Finding Nemo)"

# Pattern: number+street+suffix, then check if followed by ", (famous"
pat = re.compile(r"(\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway))(?![,.]?\s*\([^)]*(?:famous|from\s+[A-Z]))\b")

# Debug: find all matches
for m in pat.finditer(text):
    print(f'Match: "{m.group()}" at {m.start()}-{m.end()}')
    after = text[m.end():]
    print(f'  After: "{after[:40]}"')
    # Check if the lookahead should match
    check = re.match(r"[,.]?\s*\([^)]*(?:famous|from\s+[A-Z])", after)
    print(f'  Lookahead check: {bool(check)}')
    if check:
        print(f'  Lookahead match: "{check.group()}"')

# Also test lookahead directly
pat2 = re.compile(r"Way\b(?![,.]?\s*\([^)]*(?:famous|from\s+[A-Z]))")
for m in pat2.finditer(text):
    print(f'pat2 match at {m.start()}: "{m.group()}" - this means lookahead FAILED to block')