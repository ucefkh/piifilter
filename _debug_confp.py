"""Debug COMPANY FPs in the dataset."""
import re, json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

company_patterns = [(idx, cp, sc) for idx, (tn, cp, sc) in enumerate(PATTERN_DEFS) if 'COMPANY' in tn]

for ex_idx, ex in enumerate(examples):
    text = ex['text']
    expected_types = [e['type'] for e in ex['entities']]
    
    co_matches = []
    for pidx, pattern_str, score in company_patterns:
        compiled = re.compile(pattern_str)
        for m in compiled.finditer(text):
            co_matches.append((m.start(), m.end(), m.group(), score, pidx))
    
    if co_matches and 'COMPANY' not in expected_types:
        print(f'\nEx[{ex_idx}] (expected: {expected_types})')
        print(f'  Text: {repr(text[:100])}')
        for s, e, val, score, pidx in co_matches:
            # Check overlap with any expected entity
            overlap = ''
            for ent in ex['entities']:
                if ent['start'] <= s < ent['end'] or ent['start'] < e <= ent['end']:
                    overlap += f' (overlaps {ent["type"]} at [{ent["start"]}:{ent["end"]}])'
            print(f'  CO#{pidx} [{s}:{e}]={repr(val)[:60]} score={score}{overlap}')