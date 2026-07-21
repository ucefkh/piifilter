"""Debug FP: Subdomain as PERSON - check which pattern matches"""
import re
import sys
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/core/src')

from piifilter_detector_regex.patterns import PATTERN_DEFS

# Get PERSON patterns
person_patterns = [(name, pat, conf) for name, pat, conf in PATTERN_DEFS if name == 'PERSON']

text1 = 'Subdomain: api.hubbase.app'
text2 = 'Subdomain: api.tryvault.tech'

for label, text in [('text1', text1), ('text2', text2)]:
    print(f'\n=== {label}: {text!r} ===')
    for name, pat, conf in person_patterns:
        matches = list(re.finditer(pat, text))
        if matches:
            for m in matches:
                print(f'  MATCH conf={conf}: "{m.group()}" at ({m.start()},{m.end()}) => pattern: {pat[:80]}...')