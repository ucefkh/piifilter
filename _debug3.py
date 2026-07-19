"""Debug why 49 30 12345678 is missed."""
import re

pat = r"\b\d{1,4}\s+\d{2,4}(?:\s+\d{2,4}){1,2}(?:s+\d{3,4})?\b"
compiled = re.compile(pat)

val = "49 30 12345678"
print(f"Testing: '{val}'")
print(f"Pattern: {pat}")

m = compiled.search(val)
if m:
    print(f"MATCH: '{m.group()}' at [{m.start()}:{m.end()}]")
else:
    print("NO MATCH")
    
# Let's trace step by step
print("\nStep by step:")
print(f"  \b\d{1,4} => expect 1-4 digits at word boundary")
import re as _r
for start in range(len(val)):
    for end in range(start + 1, len(val) + 1):
        sub = val[start:end]
        m2 = compiled.search(sub)
        if m2:
            print(f"  sub='{sub}' -> MATCH '{m2.group()}'")
            
# Manual trace
print("\nManual trace:")
# \b\d{1,4} -> "49" (at position 0-1)
print("  Step 1: \\b\\d{1,4} => '49'")
remaining = " 30 12345678"
print(f"  Remaining: '{remaining}'")
# \s+ => " " (pos 2)
print("  Step 2: \\s+ => ' '")
# \d{2,4} => "30" (pos 3-4)
print("  Step 3: \\d{2,4} => '30'")
remaining = " 12345678"
print(f"  Remaining: '{remaining}'")
# (?: ... ){1,2}
# First iteration: \s+ => " " (pos 5), \d{2,4} => needs 2-4 digits at pos 6
print("  Step 4: First optional group: \\s+ => ' '")
remaining = "12345678"
print(f"  Remaining: '{remaining}' (8 digits)")
# \d{2,4} at 12345678 => "1234" (4 digits)
print("  Step 5: \\d{2,4} => '1234'")
remaining = "5678"
print(f"  Remaining: '{5678}'")
# Second optional group needs \s+ but there's no space before 5678
print("  Step 6: (?:\\s+\\d{3,4})? => no \\s+ before '5678', so this group fails")
print("  But {1,2} requires 1-2 repetitions, we've done one (30)")
print("  So the engine could try second iteration of {1,2}: \\s+\\d{2,4} on '12345678'")
print("  But 12345678 is 8 digits - \\d{2,4} only matches up to 4")
print("  '1234' works (4 digits), leaving '5678'")
print("  Then final (?:\\s+\\d{3,4})? needs \\s+ but '5678' has no leading space!")
print("  FAILS")

# Try a more permissive pattern
pat2 = r"\b\d{1,4}\s+\d{2,4}(?:\s+\d{3,8})?(?:\s+\d{3,4})?\b"
compiled2 = re.compile(pat2)
m2 = compiled2.search(val)
print(f"\nEnhanced pattern: '{val}' -> {'MATCH: ' + m2.group() if m2 else 'NO MATCH'}")

pat3 = r"\b\d{1,4}\s+\d{2,4}(?:\s+\d{2,8}){1,2}\b"
compiled3 = re.compile(pat3)
m3 = compiled3.search(val)
print(f"Pat3: '{val}' -> {'MATCH: ' + m3.group() if m3 else 'NO MATCH'}")