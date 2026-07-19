import json
with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

for ex in data['examples']:
    for ee in ex.get('entities', []):
        if ee['type'] == 'JWT':
            text = ex['text']
            val = ee['value']
            start, end = ee['start'], ee['end']
            span_text = text[start:end]
            print(f"Example text: {text[:80]}")
            print(f"Expected val: '{val}'")
            print(f"Span text:    '{span_text}'")
            print(f"  start={start} end={end} len={end-start}")
            # Show chars around
            print(f"  context: |{text[max(0,start-5):end+5]}|")
            print()