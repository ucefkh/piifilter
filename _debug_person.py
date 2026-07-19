import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

# Find examples with PERSON false positives
for ex in data['examples']:
    text = ex['text']
    expected_types = [e['type'] for e in ex.get('entities', [])]
    
    # Run all patterns to see what matches
    for type_name, raw_pattern, score in PATTERN_DEFS:
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text):
            if type_name == 'PERSON':
                matched_text = m.group()
                # Check if it overlaps with expected entity
                is_expected = any(
                    e['start'] <= m.start() and m.end() <= e['end'] and e['type'] == 'PERSON'
                    for e in ex.get('entities', [])
                )
                if not is_expected:
                    # Check if it overlaps with any expected entity at all
                    overlaps = any(
                        max(0, min(m.end(), e['end']) - max(m.start(), e['start'])) > 0
                        for e in ex.get('entities', [])
                    )
                    if not overlaps:
                        print(f"PERSON FP in '{text[:60]}...' -> '{matched_text}' (score={score})")