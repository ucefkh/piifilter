import json, re, sys

sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']

from piifilter_detector_regex.patterns import PATTERN_DEFS

# Check if there's a second Berlin in address
ex = examples[22]
text = ex['text']
print('Text length:', len(text))
print()

# The ADDRESS is at 42-74: "Unter den Linden 1, 10117 Berlin"
# "Berlin" at the end is at position 65-71
print('Substring 65-71:', repr(text[65:71]))
print()
print('Substring 63-69:', repr(text[63:69]))

# The expected entities are:
# CITY Berlin 11-17
# COUNTRY Germany 19-26
# ADDRESS "Unter den Linden 1, 10117 Berlin" 42-74
# But Berlin in the address (65-71) is inside the ADDRESS span. The benchmark only tracks type matches.
# The benchmark's expected_matched tracks per expected entity.
# The CITY pattern "in Berlin, Germany" (8,26) overlaps with expected CITY Berlin (11,17) but only once.
# The CITY pattern "Berlin, Germany" (11,26) overlaps with expected CITY Berlin (11,17) too, but Berlin is already matched.

print()
print('Analyzing overlap...')
# Detected:
detected_spans = [
    ('CITY', 0, 17, 0.6, "Located in Berlin"),
    ('CITY', 8, 26, 0.5, "in Berlin, Germany"),
    ('CITY', 11, 26, 0.7, "Berlin, Germany"),
    ('CITY', 11, 26, 0.4, "Berlin, Germany"),
    ('COUNTRY', 19, 26, 0.8, "Germany"),
]

for et, s, e, sc, val in detected_spans:
    print(f'  {et:10s} [{s:2d},{e:2d}) "{val}"')
    for ee in ex['entities']:
        if et == ee['type']:
            inter = max(0, min(e, ee['end']) - max(s, ee['start']))
            smallest = min(e - s, ee['end'] - ee['start'])
            if smallest > 0:
                iou = inter / smallest
                print(f'    overlap with expected "{ee["value"]}" ({ee["start"]},{ee["end"]}): inter={inter} smallest={smallest} iou={iou:.2f}')