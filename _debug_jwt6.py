import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

ex = data['examples'][82]
text = ex['text']
print(f"Text: {repr(text)}")

# The expected entity
ee = ex['entities'][0]
print(f"Expected JWT: type={ee['type']} val='{ee['value'][:30]}...' span={ee['start']}-{ee['end']}")

# Run JWT patterns
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name != 'JWT':
        continue
    compiled = re.compile(raw_pattern, re.UNICODE)
    for m in compiled.finditer(text):
        start, end = m.start(), m.end()
        intersection = max(0, min(end, ee['end']) - max(start, ee['start']))
        smallest = min(end - start, ee['end'] - ee['start'])
        ov_ratio = intersection / smallest if smallest > 0 else 0
        print(f"  Match: span={start}-{end} val='{m.group()[:40]}' ov_ratio={ov_ratio:.2f} score={score}")
        if ov_ratio >= 0.5:
            print(f"    -> Would be TP!")
        else:
            print(f"    -> Would NOT be TP")

# Also test the dedup issue - does any other pattern eat this span?
print("\nAll patterns at this location:")
for type_name, raw_pattern, score in PATTERN_DEFS:
    compiled = re.compile(raw_pattern, re.UNICODE)
    for m in compiled.finditer(text):
        if max(0, min(m.end(), ee['end']) - max(m.start(), ee['start'])) > 0:
            print(f"  {type_name}: span={m.start()}-{m.end()} val='{m.group()[:40]}'"  )