import re

text = "My street is 123 Main Street, not 123 Main St."

# Position of "123 Main St" is at 13 (first) and 34 (second)
pos = 34
pre = text[pos-4:pos]
print(f'text[{pos-4}:{pos}] = {repr(pre)}')

pat_orig = re.compile(r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

print("Full pattern from _dbg.py:")
for m in pat_orig.finditer(text):
    print(f'  "{m.group()}" at {m.start()}-{m.end()}')

# Check what (?<!not\s) at pos 34 does
# The issue: (?<!not\s) is looking back 4 chars from the \b position
# \b at pos 34 matches between ' ' (non-word) and '1' (word)
# So the lookbehind position IS at 34
# text[30:34] = " not" — does " not" match "not\\s"? No!
# So (?<!not\\s) should NOT block

# Maybe the issue is with the LOOKAHEAD?
# After "123 Main Street" match ends at 28
# After match: text[28:] = ", not 123 Main St."
# Lookahead at 28: [,.]? = ",", \s* = " ", (?:\w+\s+){0,5} = "not ", then \( needs "(" but  "1" follows
# No match -> lookahead passes -> match should work
# But wait, the FIRST match "123 Main Street" at 13-28 IS blocked by (?<!is\s)
# So the FULL pattern match only tries starting at pos 34

# At pos 34:
# (?<!is\s) checks text[31:34] = "ot " — no
# (?<!not\s) checks text[30:34] = " not" — no
# Both pass. Match: "123 Main St" at 34-45
# After match at 45: text[45:] = "."
# Lookahead at 45: [,.]? = "", \s* = "", (?:\w+\s+){0,5} = "", \( needs "(" -> no match -> lookahead passes
# So the pattern should match!

# BUT earlier it wasn't matching. Let me check if the earlier test had different pattern...
# In _dbg.py, the pattern used was: 
# r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+...Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b"
# But the current file has: r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+...Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:from\s+[A-Z][a-zA-Z]*))\b"

# Let me check the CURRENT file's pattern
print("\nCurrent file's pattern:")
# Read from file
with open('plugins/detector-regex/src/piifilter_detector_regex/patterns.py') as f:
    content = f.read()
# Find the ADDRESS pattern
import re as re2
m = re2.search(r'\(\"ADDRESS\", r\"([^"]+)\"', content.split("# Standard address:")[1])
if m:
    cur_pat_str = m.group(1)
    # Fix the escaped backslashes in the string
    cur_pat_str = cur_pat_str.replace(r"\\", "\\")
    print(f'Pattern: {cur_pat_str[:100]}...')
    cur_pat = re2.compile(cur_pat_str)
    for match in cur_pat.finditer(text):
        print(f'  CURRENT: "{match.group()}" at {match.start()}-{match.end()}')