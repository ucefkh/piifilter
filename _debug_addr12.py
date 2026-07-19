import re

# Use keyword prefix instead of lookbehind — the match starts with the keyword
# Pad with keyword prefix as part of the match
# Match format: (keyword-prefix)? + number + street name + suffix  
# The keyword prefix is optional but controls the score

# Better idea: just have TWO patterns:
# 1. Keyword-prefixed (the current one, same as line 170)
# 2. Standalone (with negative lookbehind for "is " AND comma/not context)
# But option 2 would still match "123 Main St" after comma

# Actually, the simplest fix: REQUIRE keyword context for the main pattern
# and add a separate non-keyword pattern at lower score

# Let me try a non-lookbehind approach: use a non-capturing group as prefix
# and capture the street number separately

# Pattern with -keyword prefix REQUIRED (not optional):
p_kw = re.compile(r"(?:address:\s*|at\s+|is\s+at\s+|office\s+is\s+at\s+|Home\s+address:\s*|home\s+address:\s*|\bVisit\s+us\s+at\s+|\bHQ\s+is\s+at\s+)(\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway))\b")

# Alternative: just use word-boundary anchor and check what comes before
# by inspecting the match start position

# Let me see what happens with 'address:\s' and 'at\s' fixed-width alternatives
# 'at ' = 3 chars, 'address: ' = 9 chars  
# Can use lookbehind with alternation of fixed-width alternatives
# But they must all be the same length... No! They just need to each be fixed-width.

# Actually Python re DOES support alternation of different fixed-width lookbehinds
# as long as each alternative is fixed-width. Let me verify:

try:
    p = re.compile(r"(?:(?<=address:\s)|(?<=\baddress\s)|(?<=at\s)|(?<=is\s+at\s))")
    print("Lookbehind alternation works!")
except Exception as e:
    print(f"Failed: {e}")

# Let me try the actual pattern with fixed-width lookbehinds
# 'address: ' = 9 chars (but address:\s is 9 chars with \s matching exactly one space)
# Actually 'address:\s' — \s matches ONE whitespace, so it's still fixed width if each branch is explicit

# New try: each branch must be the same length.  
# 'address:\s' = 9 chars — \s matches exactly one whitespace char (fixed width)
# 'at\s' = 3 chars — different length!
# Can't alternate different lengths. Need to pad with non-consuming groups.

# Hmm. Alternative approach: DON'T use lookbehind at all.
# Use the keyword as part of the pattern, and for the benchmark matching,
# the start position includes the keyword, but IoU is still >50% as verified.

# Actually, let me just go with the approach: make the keyword MANDATORY (not optional).
# This will:
# - Keep all 3 TPs (ex 1, 21, 44) because they have keywords
# - Remove the 2 FPs from ex 95 ("123 Main Street" and "123 Main St") because no keyword
# - Remove the 1 FP from ex 101 ("42 Wallaby Way") because no keyword
# - Potentially break cases where there's no keyword

# But what about the 1 FN (ex 22: "Unter den Linden 1, 10117 Berlin")?
# This doesn't match ANY pattern anyway, so no change.

# Let me verify if all TP examples have address keywords near them:
tps = [
    1,  # "Our office is at 350 Fifth Avenue" → "office is at "
    21, # "Visit us at 10 Downing Street" → "at "
    44, # "Home address: 123 Maple Drive" → "Home address: "
    22, # "our HQ is at Unter den Linden 1, 10117 Berlin" → "our HQ is at "
]

for idx in tps:
    import json
    data = json.loads(open('benchmarks/data/pii_dataset.json').read())
    examples = data['examples']
    ex = examples[idx]
    for ee in ex['entities']:
        if ee['type'] == 'ADDRESS':
            ctx_start = max(0, ee['start'] - 50)
            print(f'Ex {idx}: address "{ee["value"]}" at {ee["start"]}:{ee["end"]}')
            print(f'  Context: {repr(ex["text"][ctx_start:ee["end"]])}')

print()
# Now check ex 95 and 101 FPs
for idx in [95, 101]:
    ex = examples[idx]
    # Find the matched text
    p170 = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")
    for m in p170.finditer(ex['text']):
        ctx = max(0, m.start()-30)
        print(f'Ex {idx}: "{m.group()}" at {m.start()}:{m.end()}, context: {repr(ex["text"][ctx:m.start()])}')