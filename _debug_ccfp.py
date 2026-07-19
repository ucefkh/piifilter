"""Debug which CREDIT_CARD patterns match anything in the full dataset."""
import re, json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

# Find examples where CREDIT_CARD has FPs
# Look at examples where CREDIT_CARD is detected but not expected
cc_patterns = [(idx, cp, sc) for idx, (tn, cp, sc) in enumerate(PATTERN_DEFS) if 'CREDIT_CARD' in tn]

for ex_idx, ex in enumerate(examples):
    text = ex['text']
    expected_types = [e['type'] for e in ex['entities']]
    
    cc_matches = []
    for pidx, pattern_str, score in cc_patterns:
        compiled = re.compile(pattern_str)
        for m in compiled.finditer(text):
            cc_matches.append((m.start(), m.end(), m.group(), score, pidx))
    
    if cc_matches:
        has_cc_expected = 'CREDIT_CARD' in expected_types
        has_bank_expected = 'BANK_ACCOUNT' in expected_types
        has_iban_expected = 'IBAN' in expected_types
        
        if not has_cc_expected:
            print(f'\nEx[{ex_idx}] (expected: {expected_types})')
            print(f'  Text: {repr(text[:80])}')
            for s, e, val, score, pidx in cc_matches:
                print(f'  CC#{pidx} [{s}:{e}]={repr(val)[:60]} score={score}')
                # Also check if this overlaps with expected BANK_ACCOUNT or IBAN
                for ent in ex['entities']:
                    if ent['start'] <= s < ent['end'] or ent['start'] < e <= ent['end']:
                        print(f'      ^ overlaps expected {ent["type"]} at [{ent["start"]}:{ent["end"]}]={repr(ent["value"])}')