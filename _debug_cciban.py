"""Debug CREDIT_CARD patterns matching IBAN segments."""
import re, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

test_cases = [
    "My bank account is 123456789012 and my IBAN is DE89 3704 0044 0532 0130 00",
    "IBAN: DE89 3704 0044 0532 0130 00",
    "IBAN: DE89370400440532013000",
    "CC: 4111-1111-1111-1111",
    "Credit card: 5500 0000 0000 0004",
]

for text in test_cases:
    print(f'\n{"="*60}')
    print(f'Text: {repr(text)}')
    print(f'{"="*60}')
    for idx, (type_name, raw_pattern, score) in enumerate(PATTERN_DEFS):
        if 'CREDIT_CARD' in type_name:
            try:
                compiled = re.compile(raw_pattern)
                for m in compiled.finditer(text):
                    print(f'  CC#{idx} [{m.start()}:{m.end()}]={repr(m.group())[:60]} score={score}')
            except Exception as e:
                print(f'  CC#{idx} ERROR: {e}')