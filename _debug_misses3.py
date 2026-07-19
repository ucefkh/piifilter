import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

text = "Located in Berlin, Germany - our HQ is at Unter den Linden 1, 10117 Berlin"
expected_text = "Unter den Linden 1, 10117 Berlin"

# Check what ADDRESS patterns match
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'ADDRESS':
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text):
            print(f"ADDRESS: span={m.start()}-{m.end()} val='{m.group()}' score={score}")

print()
text2 = "Person: Dr. Sarah Chen works at Microsoft Research in Redmond"
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'CITY':
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text2):
            print(f"CITY: span={m.start()}-{m.end()} val='{m.group()}' score={score}")
            
print()
text3 = "City: The population of Mumbai is over 20 million."
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == 'CITY':
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text3):
            print(f"CITY: span={m.start()}-{m.end()} val='{m.group()}' score={score}")