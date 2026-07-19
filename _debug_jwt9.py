import json
with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)
ex = data['examples'][82]
print(f"Full text ({len(ex['text'])}): {repr(ex['text'])}")
for ee in ex['entities']:
    print(f"  type={ee['type']} val({len(ee['value'])}): '{ee['value']}' span={ee['start']}-{ee['end']}")

# Check what characters are actually in the JWT span
text = ex['text']
start, end = 5, 79
span = text[start:end]
print(f"\nSpan {start}-{end}: '{span}'")
print(f"Length: {len(span)}")
print(f"Chars: {[c for c in span]}")

import re
# Check: does this text have any dots?
p = r"eyJ"
compiled = re.compile(p)
for m in compiled.finditer(text):
    print(f"Found 'eyJ' at {m.start()}: context '{text[m.start()-3:m.start()+20]}'")