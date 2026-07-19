import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

for ex in data['examples']:
    text = ex['text']
    for ee in ex.get('entities', []):
        et = ee['type']
        if et not in ['CITY', 'ADDRESS', 'COUNTRY']:
            continue
        # Check if detected
        detected = False
        for type_name, raw_pattern, score in PATTERN_DEFS:
            if type_name != et:
                continue
            compiled = re.compile(raw_pattern, re.UNICODE)
            for m in compiled.finditer(text):
                start, end = m.start(), m.end()
                intersection = max(0, min(end, ee['end']) - max(start, ee['start']))
                smallest = min(end - start, ee['end'] - ee['start'])
                if smallest > 0 and intersection / smallest >= 0.5:
                    detected = True
                    break
            if detected:
                break
        if not detected:
            print(f"MISSED [{et}]: val='{ee['value']}' in '{text[:70]}...' span={ee['start']}-{ee['end']}")