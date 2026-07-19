"""Analyze which SSN examples are still missed by the regex detector."""
import json
import re
import sys

sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType

# Compile all SOCIAL_SECURITY patterns
ssn_patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == "SOCIAL_SECURITY":
        compiled = re.compile(raw_pattern, re.UNICODE)
        ssn_patterns.append((compiled, score))
        print(f"Pattern (score={score}): {raw_pattern[:80]}...")

data = json.load(open('benchmarks/data/pii_dataset_v2.json'))

# Check each SSN example
ssn_examples = [ex for ex in data['examples'] if any(e['type'] == 'SOCIAL_SECURITY' for e in ex.get('entities', []))]
missed = []
hit = []
for i, ex in enumerate(ssn_examples):
    found_any = False
    for pat, score in ssn_patterns:
        if pat.search(ex['text']):
            found_any = True
            break
    if not found_any:
        missed.append((i, ex))
    else:
        hit.append(i)

print(f'\n\n=== ANALYSIS ===')
print(f'Total SSN examples: {len(ssn_examples)}')
print(f'Hit: {len(hit)}')
print(f'Missed: {len(missed)}')

print(f'\n=== MISSED EXAMPLES ===')
for idx, (orig_i, ex) in enumerate(missed):
    val = ''
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            val = e['value']
    print(f'  Miss {idx} (orig #{orig_i}): text={repr(ex["text"][:100]):<105} value={repr(val):<40}')