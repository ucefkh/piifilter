import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset.json') as f:
    data = json.load(f)

for i, ex in enumerate(data['examples']):
    for ee in ex.get('entities', []):
        if ee['type'] == 'JWT':
            text = ex['text']
            val = ee['value']
            start, end = ee['start'], ee['end']
            print(f"Ex {i}: JWT val='{val[:40]}...' span={start}-{end} ({end-start} chars)")
            
            # Check if any JWT pattern matches
            matched = False
            for tn, rp, sc in PATTERN_DEFS:
                if tn != 'JWT':
                    continue
                compiled = re.compile(rp, re.UNICODE)
                for m in compiled.finditer(text):
                    s, e2 = m.start(), m.end()
                    intersection = max(0, min(e2, end) - max(s, start))
                    smallest = min(e2 - s, end - start)
                    if smallest > 0 and intersection / smallest >= 0.5:
                        print(f"  MATCHED by pattern {repr(rp[:60])}")
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                print(f"  NOT MATCHED by any JWT pattern!")
                # Show what DOES match
                for tn, rp, sc in PATTERN_DEFS:
                    compiled = re.compile(rp, re.UNICODE)
                    for m in compiled.finditer(text):
                        s, e2 = m.start(), m.end()
                        if max(0, min(e2, end) - max(s, start)) > 0:
                            print(f"  BUT: {tn} matches at {s}-{e2}: '{m.group()[:40]}'")