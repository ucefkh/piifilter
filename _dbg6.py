import re

text = "My street is 123 Main Street, not 123 Main St."

# Check what's before "123 Main St" at position 34
pos = text.find("123 Main St")
print(f'"123 Main St" at position {pos}')
print(f'  text[{pos-4}:{pos+1}] = {repr(text[pos-4:pos+1])}')
print(f'  text[{pos-4}:{pos}] = {repr(text[pos-4:pos])}')
print(f'  text[{pos-3}:{pos}] = {repr(text[pos-3:pos])}')

# Test (?<!not\s) at position 34
# This looks back 4 chars: text[30:34] = ",not"
# "not\s" matches "not " (n,o,t,space) 
# ",not" starts with "," — doesn't match "not\s"
# So the lookbehind should NOT block

# But earlier _dbg.py showed that "123 Main St" didn't match...
# Let me check if it's the (?<!not\s) or something else

pat = re.compile(r"\b(?<!is\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")

for m in pat.finditer(text):
    print(f'Only (?<!is\\s): "{m.group()}" at {m.start()}-{m.end()}')

# Try without any lookbehind
pat2 = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")
for m in pat2.finditer(text):
    print(f'No lookbehind: "{m.group()}" at {m.start()}-{m.end()}')