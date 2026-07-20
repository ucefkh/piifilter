"""Investigate CC/SSN recall gaps - deeper."""
from __future__ import annotations

import sys
sys.path.insert(0, "/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src")
sys.path.insert(0, "/home/ucefkh/projects/privacy-proxy-ai/core/src")

from piifilter.shared.validation import _luhn_checksum

# Check '6011111111111117837' — 19 digits, no Luhn-valid substrings?
digits = '6011111111111117837'
print(f'Full {len(digits)} digits: {digits} luhn={_luhn_checksum(digits) == 0}')

# Try all substrings of length 13-19
found = False
for length in range(13, min(20, len(digits)+1)):
    for i in range(len(digits) - length + 1):
        sub = digits[i:i+length]
        if _luhn_checksum(sub) == 0:
            print(f'  FOUND at [{i}:{i+length}]: {sub} (len={length})')
            found = True
if not found:
    print('  No Luhn-valid substrings found')

# Check '6011111111111117' (Discover)
d1 = '6011111111111117'
print(f'{d1} luhn={_luhn_checksum(d1) == 0}')

# Check the original 17-char: 60111111111111178
d2 = '60111111111111178'
print(f'{d2} luhn={_luhn_checksum(d2) == 0}')

# Now check more realistic cases where greedy Luhn would help
# Case: CC embedded in longer text: "card: 4111111111111111 and..."
test = "card: 4111111111111111 and more"
import re
# Current approach: find \b\d{13,19}\b
for m in re.finditer(r"\b\d{13,19}\b", test):
    print(f'  Current approach found: {m.group()!r} at [{m.start()}:{m.end()}]')

# Greedy approach: find \d{13,} then try substrings
for m in re.finditer(r"\d{13,}", test):
    digits2 = m.group()
    start = m.start()
    print(f'  Digit run of {len(digits2)}: {digits2!r}')
    if len(digits2) > 19:
        for i in range(len(digits2) - 12):
            for length in range(13, min(20, len(digits2) - i + 1)):
                sub = digits2[i:i+length]
                if len(sub) >= 13 and _luhn_checksum(sub) == 0:
                    print(f'    GREEDY HIT [{i}:{i+length}]: {sub}')

# Important: what about obfuscated formats that survive deobfuscation?
# After _strip_inner_separators, "4 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1" becomes "41111111111111111" (17 digits)
# The current pattern \b\d{13,19}\b catches this.
# But what about: "4 1 1 1 - 1 1 1 1 - 1 1 1 1 - 1 1 1 1"?
test2 = "4 1 1 1 - 1 1 1 1 - 1 1 1 1 - 1 1 1 1"
from piifilter.shared.deobfuscator import Deobfuscator
deob = Deobfuscator()
cleaned, log, text_for_gps = deob(test2)
stripped = Deobfuscator._strip_inner_separators(cleaned)
print(f'\nObfuscated {test2!r}:')
print(f'  cleaned={cleaned!r}')
print(f'  stripped={stripped!r}')
# Does the regex catch it now?
for m in re.finditer(r"\b\d{13,19}\b", stripped):
    print(f'  Regex finds: {m.group()!r} len={len(m.group())} luhn={_luhn_checksum(m.group()) == 0}')

print("\n--- Done ---")