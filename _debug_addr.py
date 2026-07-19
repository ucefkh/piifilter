"""Debug ADDRESS false positives."""
import json, re, sys

sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'plugins/detector-presidio/src')

data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']

from piifilter_detector_regex.patterns import PATTERN_DEFS

patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    compiled = re.compile(raw_pattern, re.UNICODE)
    patterns.append((type_name, compiled, score))

for i, ex in enumerate(examples):
    text = ex['text']
    expected_entities = ex.get('entities', [])
    
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
    
    expected_matched = [False] * len(expected_entities)
    detected_matched = [False] * len(detected)
    
    for di, det in enumerate(detected):
        for ei, ee in enumerate(expected_entities):
            if expected_matched[ei]:
                continue
            det_start, det_end = det['start'], det['end']
            exp_start, exp_end = ee['start'], ee['end']
            intersection = max(0, min(det_end, exp_end) - max(det_start, exp_start))
            smallest = min(det_end - det_start, exp_end - exp_start)
            if smallest > 0 and (intersection / smallest) >= 0.5 and det['entity_type'] == ee['type']:
                expected_matched[ei] = True
                detected_matched[di] = True
                break
    
    for di, det in enumerate(detected):
        if not detected_matched[di] and det['entity_type'] == 'ADDRESS':
            found_exp = None
            for ee in expected_entities:
                det_start, det_end = det['start'], det['end']
                exp_start, exp_end = ee['start'], ee['end']
                intersection = max(0, min(det_end, exp_end) - max(det_start, exp_start))
                smallest = min(det_end - det_start, exp_end - exp_start)
                if smallest > 0 and (intersection / smallest) >= 0.25:
                    found_exp = ee['type']
                    break
            if found_exp:
                print(f'Ex {i}: ADDRESS FP → expected was {found_exp}: "{det["value"]}" (score={det["score"]})')
            else:
                print(f'Ex {i}: ADDRESS FP (no expected): "{det["value"]}" (score={det["score"]})')