#!/usr/bin/env python3
"""Exact span calculation for CITY patterns on stripped text."""
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter.shared.deobfuscator import Deobfuscator

deob = Deobfuscator()

text = "Coordinates: 40.7128, -74.0060 (NYC) and lat: 51.5074, lon: -0.1278 (London)"
print(f"Original [{len(text)}]: {repr(text)}")

cleaned, _log, text_for_gps = deob(text)
print(f"\nCleaned [{len(cleaned)}]: {repr(cleaned)}")
print(f"GPS [{len(text_for_gps)}]: {repr(text_for_gps)}")

# Now strip inner separators from cleaned
stripped = Deobfuscator._strip_inner_separators(cleaned)
print(f"\nStripped [{len(stripped)}]: {repr(stripped)}")

print(f"\n'London' in original: idx={text.index('London')}")
print(f"'London' in cleaned: idx={cleaned.index('London') if 'London' in cleaned else 'NOT FOUND'}")
print(f"'London' in stripped: idx={stripped.index('London') if 'London' in stripped else 'NOT FOUND'}")

# The benchmark passes original text to the detector
# The detector returns spans relative to cleaned text
# Let's check what the offset map says
print("\nOffset map comparison:")
print(f"Original[69] = '{text[69]}'")
# Find corresponding char in cleaned
for i, (oc, cc) in enumerate(zip(text, cleaned)):
    if oc != cc:
        print(f"  Pos {i}: orig='{oc}' vs cleaned='{cc}'")