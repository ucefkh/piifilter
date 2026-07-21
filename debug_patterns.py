"""Debug exactly which PERSON pattern matches on the FP examples."""
import sys
import re
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter_detector_regex.patterns import PATTERN_DEFS

# Filter only PERSON patterns
person_patterns = [(name, pattern, conf) for name, pattern, conf in PATTERN_DEFS if name == 'PERSON']

# Test texts
texts = [
    "Uma Carter (uma.carter@temp-services.co.uk) works at Aviato",
    "Zack Jackson (zack.jackson@mail.company.io) works at Tyrell Corp",
    "Sofia King (sofia.king@bigpharma.com) works at Oceanic Airlines",
    "Aaron Lee (aaron.lee@temp-services.co.uk) works at Dunder Mifflin",
]

for text in texts:
    print(f"\n=== TEXT: {text} ===")
    for name, pattern, conf in person_patterns:
        for m in re.finditer(pattern, text):
            print(f"  Pattern (conf={conf}): substr='{text[m.start():m.end()]}' at [{m.start()}:{m.end()}]")