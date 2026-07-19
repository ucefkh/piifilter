import json
with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

ex = data['examples'][82]
print(f"Full text ({len(ex['text'])}):")
print(repr(ex['text']))
print()

for ee in ex['entities']:
    span = ex['text'][ee['start']:ee['end']]
    print(f"Entity: type={ee['type']}")
    print(f"  value({len(ee['value'])}): {repr(ee['value'])}")
    print(f"  span ({len(span)}): {repr(span)}")
    print(f"  start={ee['start']} end={ee['end']}")