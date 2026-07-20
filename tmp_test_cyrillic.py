"""Check Cyrillic homoglyph phone."""
import sys, re, unicodedata
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.deobfuscator import Deobfuscator

phone_patterns = [(tn, rp, sc) for tn, rp, sc in PATTERN_DEFS if tn == 'PHONE']

text = 'Phone: +1-555-123-4Ӧ97 (Cyrillic Ҧ instead of 5)'
print(f"Text: {text!r}")

for i, c in enumerate(text):
    if ord(c) > 127:
        try:
            name = unicodedata.name(c, '?')
        except:
            name = '?'
        print(f"  pos {i}: {c!r} U+{ord(c):04X} {name}")

deob = Deobfuscator()
cleaned, log, text_for_gps = deob(text)
print(f"\nCleaned: {cleaned!r}")
print(f"GPS text: {text_for_gps!r}")

for i, c in enumerate(text_for_gps):
    if ord(c) > 127:
        try:
            name = unicodedata.name(c, '?')
        except:
            name = '?'
        print(f"  Non-ASCII at {i}: {c!r} U+{ord(c):04X} {name}")

print("\nPhone patterns on GPS text:")
for tn, rp, sc in phone_patterns:
    pat = re.compile(rp)
    for m in pat.finditer(text_for_gps):
        print(f"  score={sc}: {m.group()!r} at ({m.start()},{m.end()})")

print("\nPhone patterns on cleaned:")
for tn, rp, sc in phone_patterns:
    pat = re.compile(rp)
    for m in pat.finditer(cleaned):
        print(f"  score={sc}: {m.group()!r} at ({m.start()},{m.end()})")