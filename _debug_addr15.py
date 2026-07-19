import re

text = "The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)"

# Check exact positions
p = re.compile(r"(?:(?:at\s+|is\s+at\s+))(\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b)")

for m in p.finditer(text):
    print(f'Full match: "{m.group()}" at {m.start()}-{m.end()}')
    print(f'  After match: {repr(text[m.end():m.end()+30])}')
    # What's at position m.end()?
    print(f'  Char at end: {repr(text[m.end()])}')
    # Check if the negative lookahead would see parens
    after = text[m.end():]
    print(f'  After: {repr(after[:50])}')
    # Test if \s*\( matches
    m2 = re.match(r'\s*\(', after)
    if m2:
        print(f'  \s*\( matches: "{m2.group()}"')