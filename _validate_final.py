import json, re, sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

ip_patterns = [(re.compile(p), s) for n, p, s in PATTERN_DEFS if n == 'IP_ADDRESS']
deob = Deobfuscator()

# New patterns: add decimal IP
new_patterns = [
    ("IP_ADDRESS", r"\b0x[0-9a-fA-F]{2}\.0x[0-9a-fA-F]{2}\.0x[0-9a-fA-F]{2}\.0x[0-9a-fA-F]{2}\b", 0.85),
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)/\d{1,2}\b", 0.90),
    ("IP_ADDRESS", r"\b0[0-7]{1,4}(?:\.0[0-7]{1,4}){3}\b", 0.85),
    ("IP_ADDRESS", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\s+){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", 0.80),
    ("IP_ADDRESS", r"\b0x[0-9a-fA-F]{2}\.\d{1,3}\.0x[0-9a-fA-F]{2}\.\d{1,3}\b", 0.75),
    # Decimal IP: 3232235876 — a 32-bit integer up to ~4.3B (10 digits)
    ("IP_ADDRESS", r"\b(?:[1-9]\d{6,9})\b", 0.65),
]

all_patterns = ip_patterns + [(re.compile(p), s) for n, p, s in new_patterns]

unmatched = []
for ex in data['examples']:
    for entity in ex.get('entities', []):
        if entity['type'] != 'IP_ADDRESS':
            continue
        cleaned, _ = deob(ex['text'])
        if not any(p.search(cleaned) for p, _ in all_patterns):
            unmatched.append({'value': entity['value'], 'text': ex['text']})

print(f"Still unmatched with ALL patterns (including decimal): {len(unmatched)}")
for u in unmatched:
    print(f"  {repr(u['value']):40s} | {repr(u['text'][:80])}")