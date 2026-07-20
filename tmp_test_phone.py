"""Test if phone patterns match the pre-strip text."""
import sys, re
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.deobfuscator import Deobfuscator

# The GPS text (pre-strip) for the URL-encoded phone
text_gps = 'URL-encoded phone: +1-555-123-4567'

print(f"GPS text: {text_gps!r}")
print()

# Find phone patterns and test each
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'PHONE':
        pat = re.compile(raw_pattern)
        for m in pat.finditer(text_gps):
            print(f"  PHONE pattern (score={score}): {m.group()!r} at {m.start()}-{m.end()}")
            print(f"    Pattern: {raw_pattern[:80]}...")

print("\n--- Stripped text ---")
stripped = Deobfuscator._strip_inner_separators(text_gps)
print(f"Stripped: {stripped!r}")
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'PHONE':
        pat = re.compile(raw_pattern)
        for m in pat.finditer(stripped):
            print(f"  PHONE pattern (score={score}): {m.group()!r} at {m.start()}-{m.end()}")