"""Debug which CREDIT_CARD patterns match bank account numbers."""
import re, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

test_cases = [
    "My bank account is 123456789012",  # BANK_ACCOUNT example
    "bank account 98765432109876543210",
]

for text in test_cases:
    print(f'\nText: {repr(text)}')
    for idx, (type_name, raw_pattern, score) in enumerate(PATTERN_DEFS):
        if 'CREDIT_CARD' in type_name:
            try:
                compiled = re.compile(raw_pattern)
                for m in compiled.finditer(text):
                    print(f'  CC#{idx} [{m.start()}:{m.end()}]={repr(m.group())[:60]} score={score}')
            except Exception as e:
                print(f'  CC#{idx} ERROR: {e}')