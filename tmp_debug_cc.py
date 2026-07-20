#!/usr/bin/env python3
"""Debug the exact case of '6011-1111-1111-1117' span mismatch."""
import re
from piifilter.shared.deobfuscator import Deobfuscator

# The problematic case
text = " 3782-822463-10005 (Amex) and 6011-1111-1111-1117 (Discover)"
e_start = 38  # Assuming start of '6011-1111-1111-1117'
e_end = 57
span = text[e_start:e_end]
print(f"Original span: {span!r} at [{e_start}:{e_end}]")

deob = Deobfuscator()
cleaned, log, gps_text = deob(text)
print(f"Cleaned text: {cleaned!r}")

stripped = Deobfuscator._strip_inner_separators(cleaned)
print(f"Stripped text: {stripped!r}")

# What's at the same coordinates in stripped?
if e_end <= len(stripped):
    stripped_span = stripped[e_start:e_end]
    print(f"Stripped at same coords: {stripped_span!r}")
    print(f"Stripped digits: {''.join(c for c in stripped_span if c.isdigit())!r}")
else:
    print(f"Stripped len={len(stripped)} < e_end={e_end}")

# Check the actual position by searching
cc_pos = cleaned.find("6011")
print(f"\n'6011' found at position {cc_pos} in cleaned")
if cc_pos >= 0:
    cc_stripped = stripped[cc_pos:cc_pos+16]
    print(f"CC at adjusted pos in stripped: {cc_stripped!r}")

# The key question: does the deobfuscator change the '6' before '011'?
# Check what happens to "6011-1111-1111-1117" through the pipeline
text2 = "6011-1111-1111-1117"
c2, _, _ = deob(text2)
print(f"\nDirect test: {text2!r} -> {c2!r}")
s2 = Deobfuscator._strip_inner_separators(c2)
print(f"Stripped: {s2!r}")

# Now the REAL issue: the span positions shift after deobfuscation!
# The benchmark uses original text positions but detection runs on stripped text.
# Let's verify how the benchmark compares positions.
print("\n--- Benchmark position comparison ---")
# If deobfuscation adds/removes chars, positions shift
print(f"Original text: {text}")
print(f"Cleaned text:  {cleaned}")
print(f"Original '6011' at position {text.find('6011')}")
print(f"Cleaned '6011' at position {cleaned.find('6011')}")
print(f"Length diff: deobfuscation changed len {len(text)} -> {len(cleaned)}")

# Check if there's a leading space difference
for i, (a, b) in enumerate(zip(text, cleaned)):
    if a != b:
        print(f"First diff at pos {i}: {a!r} vs {b!r}")
        break