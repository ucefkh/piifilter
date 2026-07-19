import json
import re
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

# Current IP patterns (compiled)
ip_patterns = [(re.compile(p), s) for n, p, s in PATTERN_DEFS if n == 'IP_ADDRESS']

deob = Deobfuscator()

# New patterns to add
new_patterns = [
    # 1. Hex IP: 0xc0.0xa8.0x00.0x01 (dots)
    ("HEX_DOT", r"\b0x[0-9a-fA-F]{2}\.0x[0-9a-fA-F]{2}\.0x[0-9a-fA-F]{2}\.0x[0-9a-fA-F]{2}\b", 0.85),
    # 2. Hex IP with spaces: 0xc0 . 0xa8 . 0x00 . 0x01
    ("HEX_SPACE", r"\b0x[0-9a-fA-F]{2}\s*\.\s*0x[0-9a-fA-F]{2}\s*\.\s*0x[0-9a-fA-F]{2}\s*\.\s*0x[0-9a-fA-F]{2}\b", 0.80),
    # 3. CIDR: 192.168.1.100/16
    ("CIDR", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)/\d{1,2}\b", 0.90),
    # 4. Octal IP with dots: 012.0130.00.01 (each octet is 3-digit octal)
    ("OCTAL_DOT", r"\b0[0-7]{2,3}\.0[0-7]{2,3}\.0[0-7]{2,3}\.0[0-7]{2,3}\b", 0.75),
    # 5. Octal IP with mixed widths: 012.0130.00.01, 0254.020.00.01, 041.0250.0225.0247
    # More flexible: allows 2-4 octal digits
    ("OCTAL_DOT_FLEX", r"\b0[0-7]{1,4}(?:\.0[0-7]{1,4}){3}\b", 0.85),
    # 6. Space-separated integer groups that = an IP: "192 168 1 100", "10 0 0 5" etc.
    # Each group: 1-3 digits, separated by spaces (1 or more)
    ("SPACE_IP", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\s+){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", 0.80),
    # 7. Mixed hex IP: 0x22.0x23.44.0xab (some dotted-hex, some dotted-decimal)
    ("HEX_MIXED", r"\b0x[0-9a-fA-F]{2}\.\d{1,3}\.0x[0-9a-fA-F]{2}\.\d{1,3}\b", 0.75),
    # 8. Space+dot IP: "192 . 168 . 1 . 100" — already caught by deobfuscator! No need.
    # 9. "192.168.1.1" inside string concatenation — needs `"192" + "." + "168"` deobfuscation
    # This is hard; won't add pattern since it's a single edge case
]

new_compiled = [(re.compile(p), name, s) for name, p, s in new_patterns]

# Find unmatched entries
unmatched = []
for ex in data['examples']:
    for entity in ex.get('entities', []):
        if entity['type'] != 'IP_ADDRESS':
            continue
        text = ex['text']
        cleaned, _ = deob(text)
        raw_match = any(pat.search(cleaned) for pat, _ in ip_patterns)
        if raw_match:
            continue
        new_match = False
        new_matches = []
        for pat, name, s in new_compiled:
            # Test on both raw and cleaned
            m1 = pat.search(ex['text'])
            m2 = pat.search(cleaned)
            if m1 or m2:
                new_match = True
                new_matches.append(name)
        unmatched.append({
            'value': entity['value'],
            'new_match': new_match,
            'new_matches': new_matches,
            'text': ex['text']
        })

matched_by_new = sum(1 for u in unmatched if u['new_match'])
print(f"Unmatched after deob + current patterns: {len(unmatched)}")
print(f"Matched by new patterns: {matched_by_new}")
print(f"Still unmatched: {len(unmatched) - matched_by_new}")

print("\n=== Still unmatched (need investigation) ===")
for u in unmatched:
    if not u['new_match']:
        print(f"  {repr(u['value']):40s} | {repr(u['text'][:80])}")

print("\n=== Matched by new patterns ===")
for u in unmatched:
    if u['new_match']:
        print(f"  {repr(u['value']):40s} | patterns: {u['new_matches']}")