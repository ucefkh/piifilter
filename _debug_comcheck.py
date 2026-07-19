"""Check all COMPANY entities are covered by current patterns."""
import re, json, sys
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

data = json.load(open('benchmarks/data/pii_dataset.json'))
examples = data['examples']

company_patterns = [(idx, cp, sc) for idx, (tn, cp, sc) in enumerate(PATTERN_DEFS) if 'COMPANY' in tn]

all_companies = []
for ex_idx, ex in enumerate(examples):
    for ent in ex['entities']:
        if ent['type'] == 'COMPANY':
            all_companies.append((ex_idx, ent, ex['text']))

print(f'Total COMPANY entities in dataset: {len(all_companies)}')
print()

for ex_idx, ent, text in all_companies:
    matched = False
    matched_by = []
    for pidx, pattern_str, score in company_patterns:
        compiled = re.compile(pattern_str)
        for m in compiled.finditer(text):
            s, e = m.start(), m.end()
            if ent['start'] <= s < ent['end'] or ent['start'] < e <= ent['end']:
                matched = True
                matched_by.append(f'CO#{pidx}(score={score}):{repr(m.group())[:40]}')
    
    if not matched:
        print(f'  MISSED Ex[{ex_idx}]: {ent["value"]} at [{ent["start"]}:{ent["end"]}]')
        print(f'    Text: {repr(text[:120])}')
    else:
        print(f'  OK Ex[{ex_idx}]: {ent["value"]:30s} matched by {matched_by[0]}')