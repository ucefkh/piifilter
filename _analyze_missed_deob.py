"""Analyze which SSN examples are still missed — AFTER deobfuscation."""
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

from piifilter.shared.deobfuscator import Deobfuscator
deob = Deobfuscator()

data = json.load(open('benchmarks/data/pii_dataset_v2.json'))

# Check each SSN example — after deobfuscation
ssn_examples = [ex for ex in data['examples'] if any(e['type'] == 'SOCIAL_SECURITY' for e in ex.get('entities', []))]
missed = []
hit = []
for i, ex in enumerate(ssn_examples):
    cleaned, _log = deob(ex['text'])
    found_any = False
    for pat, score in ssn_patterns:
        if pat.search(cleaned):
            found_any = True
            break
    if not found_any:
        missed.append((i, ex, cleaned))
    else:
        hit.append(i)

print(f'Total SSN examples: {len(ssn_examples)}')
print(f'Hit (after deobfuscation): {len(hit)}')
print(f'Missed (after deobfuscation): {len(missed)}')

print(f'\n=== MISSED EXAMPLES (after deobfuscation) ===')
for idx, (orig_i, ex, cleaned) in enumerate(missed):
    val = ''
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            val = e['value']
    print(f'\n  Miss {idx} (orig #{orig_i}):')
    print(f'    Text:   {repr(ex["text"][:100])}')
    print(f'    Cleaned: {repr(cleaned[:150])}')
    print(f'    Value:  {repr(val)}')

print(f'\n\n=== WHAT CURRENT PATTERNS MATCH (on cleaned text) ===')
for idx, (orig_i, ex, cleaned) in enumerate(missed):
    val = ''
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            val = e['value']
    print(f'\nMiss {idx} (clean={repr(cleaned[:150]):<155}) value={repr(val):<40}')
    for pi, (pat, score) in enumerate(ssn_patterns):
        m = pat.search(cleaned)
        if m:
            print(f'    Pattern {pi} (score={score}) MATCHES: {repr(m.group())}')