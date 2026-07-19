import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

# Detect all matches per type
for ex in data['examples']:
    text = ex['text']
    expected_entities = ex.get('entities', [])
    
    # Collect all detections
    detections = []
    for type_name, raw_pattern, score in PATTERN_DEFS:
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text):
            detections.append((type_name, m.start(), m.end(), m.group()))
    
    # For each PERSON detection, check overlaps
    for dt, ds, de, dg in detections:
        if dt == 'PERSON':
            is_tp = False
            for ee in expected_entities:
                if ee['type'] == 'PERSON':
                    ov = max(0, min(de, ee['end']) - max(ds, ee['start']))
                    smallest = min(de - ds, ee['end'] - ee['start'])
                    if smallest > 0 and ov/smallest >= 0.5:
                        is_tp = True
                        break
            if not is_tp:
                # Check if it overlaps a non-PERSON expected entity
                overlaps_other = False
                for ee in expected_entities:
                    if ee['type'] != 'PERSON':
                        ov = max(0, min(de, ee['end']) - max(ds, ee['start']))
                        if ov > 0:
                            overlaps_other = True
                            print(f"PERSON FP (confused): text='{text[:60]}' -> '{dg}' overlaps expected {ee['type']}='{ee['value']}'")
                            break
                if not overlaps_other:
                    print(f"PERSON FP (NONE): text='{text[:60]}' -> '{dg}'")