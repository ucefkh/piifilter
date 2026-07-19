import re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

text = 'JWT: eyJzdW...IyfQ'
print(f"Testing JWT on: {text}")
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name != 'JWT':
        continue
    compiled = re.compile(raw_pattern, re.UNICODE)
    for m in compiled.finditer(text):
        print(f"  JWT match: span={m.start()}-{m.end()} val='{m.group()}' score={score}")