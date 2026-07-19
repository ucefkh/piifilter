import json
import re
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS

# Load dataset
with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

# Compile IP patterns
ip_patterns = [(re.compile(p), name, score) for name, p, score in PATTERN_DEFS if name == 'IP_ADDRESS']

deob = Deobfuscator()

# Find all IP_ADDRESS entities and test with deobfuscation
results = {"matched_raw": 0, "matched_deob": 0, "unmatched": [], "deob_only": []}
for example in data['examples']:
    for entity in example.get('entities', []):
        if entity['type'] != 'IP_ADDRESS':
            continue
        text = example['text']
        # Test raw
        raw_match = any(pat.search(text) for pat, _, _ in ip_patterns)
        # Test deobfuscated
        cleaned, _ = deob(text)
        deob_match = any(pat.search(cleaned) for pat, _, _ in ip_patterns)
        
        if raw_match:
            results["matched_raw"] += 1
            if not deob_match:
                print(f"UNEXPECTED: raw matched but deob didn't: {repr(entity['value'])}")
        elif deob_match:
            results["deob_only"].append(entity['value'])
            results["matched_deob"] += 1
        else:
            results["unmatched"].append({
                'value': entity['value'],
                'text': text,
                'start': entity['start'],
                'end': entity['end']
            })

print(f"\n=== Results across all {len([e for ex in data['examples'] for e in ex.get('entities', []) if e['type'] == 'IP_ADDRESS'])} IP entries ===")
print(f"Raw pattern match:         {results['matched_raw']}")
print(f"Deobfuscator-only match:   {results['deob_only']}")
print(f"Total after deob:          {results['matched_raw'] + results['matched_deob']}")
print(f"Still unmatched:           {len(results['unmatched'])}")

# Categorize truly unmatched
cats = {}
for entry in results['unmatched']:
    v = entry['value']
    t = entry['text']
    if v.startswith('0x') or '0x' in v.lower():
        cat = 'hex-ip'
    elif re.match(r'^\d+$', v.replace(' ', '').replace('.', '')):
        # Check if it's a decimal IP
        if v.replace(' ', '').replace('.', '').isdigit():
            digits = v.replace(' ', '').replace('.', '')
            if len(digits) >= 7 and len(digits) <= 12:
                cat = 'decimal-ip'
            else:
                cat = 'other-digit'
        else:
            cat = 'other'
    elif '/' in v:
        cat = 'cidr'
    elif ' . ' in v:
        cat = 'spaced-dot-fail'
    elif v.startswith('0') and '.' in v:
        cat = 'octal-ip'
    elif ' ' in v.strip():
        cat = 'space-separated'
    else:
        cat = 'other'
    cats.setdefault(cat, []).append(v)

print("\n=== Unmatched categories ===")
for cat, vals in sorted(cats.items()):
    print(f"\n  {cat} ({len(vals)}):")
    for v in vals:
        # show a snippet of context
        ctx = ""
        for ex in data['examples']:
            for e in ex['entities']:
                if e['type'] == 'IP_ADDRESS' and e['value'] == v:
                    s = e['start']
                    ctx = ex['text'][max(0,s-30):s+len(v)+20]
                    break
        print(f"    {repr(v):40s}  ctx: {repr(ctx)[:80]}")