import re

text = "My street is 123 Main Street, not 123 Main St."

# Position of "123 Main St" is at 13 (first) and 34 (second)
# For the second match at pos 34:
# (?<!not\s) looks back 4 chars from pos 34: text[30:34]
print(f'text[30:34] = {repr(text[30:34])}')
# text[30:34] = " not" — is " not" matching "not\\s"?
# "not\\s" = [n][o][t][\\s] = "not "
# " not" = [ ][n][o][t]
# NO MATCH. So (?<!not\\s) DOES NOT block.

# So why was "123 Main St" blocked in my earlier test?
# Let me re-test with the EXACT pattern from _dbg
p = re.compile(r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

for m in p.finditer(text):
    print(f'Full pattern: "{m.group()}" at {m.start()}-{m.end()}')

# Let me check the earlier _dbg.py pattern more carefully
# It had (?<!not\\s) which is 4 chars, AND it's a lookbehind before the first \b
# But \b is zero-width... the lookbehind is at the position of \b
# For pos 34, (?<!not\\s) checks text[30:34] = " not"
# "not\\s" is "not " - 4 chars, text[30:34] is " not" which is " not" (space n o t)
# " not" != "not " — so NOT blocked

# BUT in _dbg.py the pattern matched (not blocked)... wait, the test said "not matched":
# ✗ No for: My street is 123 Main Street, not 123 Main St.
# So BOTH 123 Main Street AND 123 Main St were not matched

# Let me check what the issue is for 123 Main Street at pos 13
# (?<!is\\s) at pos 13 checks text[10:13] = "is " 
# "is\\s" is "is " — MATCHES! So blocked.

# And for 123 Main St at pos 34:
# (?<!not\\s) at pos 34 checks text[30:34] = " not"
# "not\\s" is "not " — " not" != "not " — NOT blocked
# So why was it blocked in _dbg.py?

# Maybe the negative LOOKAHEAD is blocking it?
# After "123 Main St" (34-45), the next text is "."
# Lookahead: (?![,.]?\s*(?:\w+\s+){0,5}\([^)]*...)
# At pos 45: "." — [,.]? matches "."
# Then \s* matches empty
# Then (?:\w+\s+){0,5} matches empty (no more chars)
# Then \( — char at 45 is "." not "("
# So the lookahead PASSES (doesn't find media reference)
# The lookahead should NOT block!

# So why did _dbg.py say no match?
# Let me check if _dbg.py has a DIFFERENT pattern

# Re-reading _dbg.py:
# It used: r"\b(?<!is\s)(?<!not\s)\d{1,5}..." with the original lookahead
# I think the issue was the lookahead had from\s+[A-Z] which at pos 45 after "." doesn't match "(", so passes

# ACTUALLY WAIT - in _dbg.py the result was:
# ✗ No for: My street is 123 Main Street, not 123 Main St.
# But we see here that (?<!not\\s) doesn't block pos 34.

# Let me check the FULL match at position 34 by stepping through
# Maybe \b doesn't match at position 34?
print(f'\\b at pos 34: {re.search(r"\\b", text, 34)}')
print(f'Character at 33: {repr(text[33])}')
print(f'Character at 34: {repr(text[34])}')
# \b matches between word and non-word. 33 = ' ', 34 = '1'
# ' ' is non-word, '1' is word → \b SHOULD MATCH at 34

# Check the lookahead at the END of the match
# After "123 Main St" which ends at position 45
m = re.search(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b", text, 34)
if m:
    print(f'Match at {m.start()}-{m.end()}: "{m.group()}"')
    end = m.end()
    print(f'After match: {repr(text[end:end+30])}')
    
    # The full pattern has a trailing \b AFTER the lookahead!
    # So: ...Parkway)(?![,.]?...))\b
    # The \b is at the END of the full pattern.
    # After "123 Main St" the match is at 45, \b needs word boundary at 45
    # Char at 45 is "." — word char? No.
    # So \b at position 45 checks: text[44] = 't' (word), text[45] = '.' (non-word)
    # That IS a word boundary! \b matches.
    
    # So the lookahead at position 45 should pass.
    # Let me check: lookahead is at position 45, text is "."
    
    # Actually, I bet the issue is that the lookahead was the OLD version:
    # (?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))
    # At pos 45: text[45:] = "."
    # [,.]? matches "."
    # Then \s* matches ""
    # Then (?:\w+\s+){0,5} matches "" (empty)
    # Then \( needs to match "(" but we have "." (end of string)
    # So the inner pattern doesn't match → lookahead passes → should match

# Let me just directly test the pattern from _dbg.py again
pat_orig = re.compile(r"\b(?<!is\s)(?<!not\s)\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

print("\nFull pattern from _dbg.py:")
for m in pat_orig.finditer(text):
    print(f'  "{m.group()}" at {m.start()}-{m.end()}')