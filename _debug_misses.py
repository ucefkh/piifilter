import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

# Check specific problem examples
fn_cases = {
    'CITY': ['Paris', 'Mumbai', 'Berlin', 'London'],
    'ADDRESS': ['10 Downing Street'],
    'PHONE': [],
    'JWT': [],
    'GPS': [],
}

for ex in data['examples']:
    text = ex['text']
    for ee in ex.get('entities', []):
        et = ee['type']
        val = ee['value']
        
        # Check if this expected entity is detected
        detected = False
        for type_name, raw_pattern, score in PATTERN_DEFS:
            compiled = re.compile(raw_pattern, re.UNICODE)
            for m in compiled.finditer(text):
                if type_name == et:
                    start, end = m.start(), m.end()
                    intersection = max(0, min(end, ee['end']) - max(start, ee['start']))
                    smallest = min(end - start, ee['end'] - ee['start'])
                    if smallest > 0 and intersection / smallest >= 0.5:
                        detected = True
                        break
            if detected:
                break
        
        if not detected:
            print(f"MISSED [{et}]: '{val}' in '{text[:80]}...'")
            print(f"  Expected span: {ee['start']}-{ee['end']}")
            
            # Show all regex matches near that span
            for type_name, raw_pattern, score in PATTERN_DEFS:
                compiled = re.compile(raw_pattern, re.UNICODE)
                for m in compiled.finditer(text):
                    if max(0, min(m.end(), ee['end']) - max(m.start(), ee['start'])) > 0:
                        print(f"  Near-match: type={type_name} span={m.start()}-{m.end()} val='{m.group()}' score={score}")
            print()