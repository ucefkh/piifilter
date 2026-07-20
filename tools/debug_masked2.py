"""Debug MASKED_SSN detection on example 179."""
import sys, re
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')

import piifilter_detector_regex.patterns as pat_mod
text = 'SSN last-4: 6789. Full: XXX-XX-6789'
print('=== MASKED PATTERNS ===')
for et, pattern, conf in pat_mod.MASKED_PATTERNS:
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    for m in matches:
        print(f'{et} conf={conf}: matched={repr(m.group())} at {m.start()}-{m.end()}')