import re

after = ", Sydney (famous from Finding Nemo)"
# The pattern: [,]?\s*\([^)]*famous
# Let me debug
p = re.compile(r"[,]?\s*\([^)]*famous")
m = p.match(after)
print(f'Direct match: {bool(m)}')
if m:
    print(f'Match: "{m.group()}"')
else:
    # Try step by step
    m1 = re.match(r"[,]?", after)
    print(f'[,]?: "{m1.group()}" ({m1.end()})')
    
    m2 = re.match(r"[,]?\s*", after)
    print(f'[,]?\\s*: "{m2.group()}" ({m2.end()})')
    
    after_m2 = after[m2.end():]
    print(f'After [,]?\\s*: "{after_m2}"')
    
    m3 = re.match(r"\(", after_m2)
    print(f'\\( : {bool(m3)}')
    if m3:
        print(f'Match: "{m3.group()}"')
    
    # The issue is: after "42 Wallaby Way" (ends at 14), the remaining text is
    # ", Sydney (famous from Finding Nemo)"
    # [,]? matches "," at position 14
    # \s* matches " " at position 15
    # But then \( looks for "(" at position 16, which is "S" (from "Sydney")
    # So \( doesn't match!
    
    print()
    print(f'Position 14: {repr(after[0])}')
    print(f'Position 15: {repr(after[1])}')
    print(f'Position 16: {repr(after[2])}: {repr(after[:20])}')