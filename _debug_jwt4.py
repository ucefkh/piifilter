import json
with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

ex = data['examples'][8]  # JWT example
print(f"Text ({len(ex['text'])}): '{ex['text']}'")
for ee in ex['entities']:
    print(f"  Entity: type={ee['type']} value({len(ee['value'])}): '{ee['value']}' start={ee['start']} end={ee['end']}")
    # Show actual chars in that span
    span = ex['text'][ee['start']:ee['end']]
    print(f"  Span text: '{span}' ({len(span)} chars)")
    print(f"  Match value==span: {span == ee['value']}")

# Also check the index that's failing
print()
print("=== ALL examples with JWT entities ===")
for i, ex in enumerate(data['examples']):
    for ee in ex.get('entities', []):
        if ee['type'] == 'JWT':
            span = ex['text'][ee['start']:ee['end']]
            print(f"  Ex {i}: text='{ex['text'][:60]}...'")
            print(f"    value='{ee['value']}' ({len(ee['value'])} chars) span='{span}' ({len(span)} chars) match={span == ee['value']}")