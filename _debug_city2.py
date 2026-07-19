import json, re, sys

sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']

from piifilter_detector_regex.patterns import PATTERN_DEFS

# Look at example 22 in detail
ex = examples[22]
text = ex['text']
expected_entities = ex['entities']

print(f'Text: {repr(text)}')
print(f'Expected entities: {json.dumps(expected_entities, indent=2)}')
print()

# Show all detected entities
patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    compiled = re.compile(raw_pattern, re.UNICODE)
    patterns.append((type_name, compiled, score))

detected = []
for type_name, pattern, score in patterns:
    for match in pattern.finditer(text):
        start, end = match.start(), match.end()
        if start == end:
            continue
        detected.append({
            'entity_type': type_name,
            'value': match.group(),
            'start': start,
            'end': end,
            'score': score,
        })

for d in sorted(detected, key=lambda x: x['start']):
    print(f'  Detected: {d["entity_type"]:15s} "{d["value"]:40s}" start={d["start"]:3d} end={d["end"]:3d} score={d["score"]}')