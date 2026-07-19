import re

text = "42 Wallaby Way, Sydney (from the movie Finding Nemo)"

# Check the negative lookahead  
# First find the address match
pat_prefix = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)")

for m in pat_prefix.finditer(text):
    print(f'Match: "{m.group()}" at {m.start()}-{m.end()}')
    after = text[m.end():]
    print(f'  After: "{after}"')
    
    # Test the negative lookahead part
    lookahead_pat = re.compile(r"(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:from\s+[A-Z][a-zA-Z]*))")
    lm = lookahead_pat.match(text, m.end())
    print(f'  Lookahead match: {lm is not None}')
    if lm:
        print(f'  rmaining after lookahead: "{text[lm.end():]}"')
    
    # Let me see what the lookahead actually matches
    # The lookahead is negative, so it checks if the inner pattern matches
    inner_pat = re.compile(r"[,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:from\s+[A-Z][a-zA-Z]*)")
    im = inner_pat.match(text, m.end())
    print(f'  Inner pattern matches at {m.end()}: {im is not None}')
    if im:
        print(f'  Inner match: "{im.group()}" (span {im.start()}-{im.end()})')
    
    # Check step by step
    pos = m.end()
    print(f'  Position {pos}: char={repr(text[pos])}')
    
    # [,.]?
    m1 = re.match(r"[,.]?", text[pos:])
    print(f'  [,.]? at pos: {bool(m1)}, "{m1.group()}"')
    pos2 = pos + m1.end()
    
    # \s*
    m2 = re.match(r"\s*", text[pos2:])
    print(f'  \\s* at pos {pos2}: "{m2.group()}"')
    pos3 = pos2 + m2.end()
    
    # (?:\w+\s+){0,5}
    m3 = re.match(r"(?:\w+\s+){0,5}", text[pos3:])
    print(f'  (?:\\w+\\s+){{0,5}} at pos {pos3}: "{m3.group()}"')
    pos4 = pos3 + m3.end()
    
    # \(
    print(f'  Next char at {pos4}: {repr(text[pos4])}')
    if text[pos4] == '(':
        print(f'   Found ( at {pos4}!')
        # Inside parens: [^)]*from\s+[A-Z]
        paren_content = text[pos4:]
        m4 = re.match(r"\([^)]*(?:from\s+[A-Z][a-zA-Z]*)", paren_content)
        print(f'   Paren content: "{paren_content[:80]}"')
        print(f'   Matches from-inside-paren pattern: {m4 is not None}')
        if m4:
            print(f'   Inner match: "{m4.group()}"')
    else:
        print(f'   Char is {repr(text[pos4])} — not (')