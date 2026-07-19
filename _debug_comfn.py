"""Debug which COMPANY example was missed after the fix."""
import re, json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

company_patterns = [(idx, cp, sc) for idx, (tn, cp, sc) in enumerate(PATTERN_DEFS) if 'COMPANY' in tn]

for ex_idx, ex in enumerate(examples):
    text = ex['text']
    expected = [e for e in ex['entities'] if e['type'] == 'COMPANY']
    if not expected:
        continue
    
    co_matches = []
    for pidx, pattern_str, score in company_patterns:
        compiled = re.compile(pattern_str)
        for m in compiled.finditer(text):
            co_matches.append((m.start(), m.end(), m.group(), score, pidx))
    
    found_any = False
    for s, e, val, score, pidx in co_matches:
        for ent in expected:
            if ent['start'] <= s < ent['end'] or ent['start'] < e <= ent['end']:
                found_any = True
    
    if not found_any:
        print(f'Ex[{ex_idx}] COMPANY MISSED!')
        print(f'  Text: {repr(text[:120])}')
        for ent in expected:
            print(f'  Expected: {ent["type"]} at [{ent["start"]}:{ent["end"]}]={repr(ent["value"])}')
        print(f'  Detected:')
        for s, e, val, score, pidx in co_matches:
            print(f'    CO#{pidx} [{s}:{e}]={repr(val)[:60]} score={score}')