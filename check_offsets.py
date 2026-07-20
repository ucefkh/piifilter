#!/usr/bin/env python3
"""Check span offsets from deobfuscator."""
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.deobfuscator import Deobfuscator

deob = Deobfuscator()

# Check: London in coordinates text
text = "Coordinates: 40.7128, -74.0060 (NYC) and lat: 51.5074, lon: -0.1278 (London)"
print(f"Original text len={len(text)}")
print(f"  'London' original idx: {text.index('London')}")

cleaned, _log, _gps = deob(text)
print(f"Cleaned text len={len(cleaned)}")
print(f"Cleaned: {repr(cleaned)}")
print(f"  'London' cleaned idx: {cleaned.index('London') if 'London' in cleaned else 'NOT FOUND'}")

# Show diff
for i, (a, b) in enumerate(zip(text, cleaned)):
    if a != b:
        print(f"  Diff at {i}: orig='{a}' vs cleaned='{b}'")
        break