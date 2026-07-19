import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

# Check specific JWT issue
for ex in data['examples']:
    text = ex['text']
    for ee in ex.get('entities', []):
        if ee['type'] == 'JWT':
            val = ee['value']
            for type_name, raw_pattern, score in PATTERN_DEFS:
                compiled = re.compile(raw_pattern, re.UNICODE)
                for m in compiled.finditer(text):
                    if type_name == 'JWT':
                        print(f"JWT match: type={type_name} span={m.start()}-{m.end()} val='{m.group()[:50]}' score={score}")
            print(f"  Expected: '{val[:50]}' span={ee['start']}-{ee['end']}")
            
# Check CITY false positives  
print("\n=== CITY false positives ===")
for ex in data['examples']:
    text = ex['text']
    expected_cities = {e['value'] for e in ex.get('entities', []) if e['type'] == 'CITY'}
    
    for type_name, raw_pattern, score in PATTERN_DEFS:
        if type_name != 'CITY':
            continue
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text):
            # Check if this match overlaps with expected CITY entity
            is_tp = False
            for ee in ex.get('entities', []):
                if ee['type'] == 'CITY':
                    intersection = max(0, min(m.end(), ee['end']) - max(m.start(), ee['start']))
                    smallest = min(m.end() - m.start(), ee['end'] - ee['start'])
                    if smallest > 0 and intersection / smallest >= 0.5:
                        is_tp = True
                        break
            if not is_tp:
                # Check if overlaps any expected entity at all
                overlaps_any = any(
                    max(0, min(m.end(), ee['end']) - max(m.start(), ee['start'])) > 0
                    for ee in ex.get('entities', [])
                )
                if not overlaps_any:
                    print(f"  FP: text='{text[:60]}' -> CITY '{m.group()}'")