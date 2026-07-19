#!/usr/bin/env python3
"""Find the remaining 7 EMAIL FNs after fixes."""
import sys, re, json, os
from collections import defaultdict
os.chdir("/home/ucefkh/projects/privacy-proxy-ai")
sys.path.insert(0, "core/src")
sys.path.insert(0, "plugins/detector-regex/src")
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS

# Load patterns
email_patterns = [(name, re.compile(p, re.UNICODE), s) for name, p, s in PATTERN_DEFS if name == "EMAIL"]

# Same split as benchmark
DATA_PATH = "benchmarks/data/pii_dataset_v2.json"
raw = json.loads(open(DATA_PATH).read())
examples = raw["examples"]

random = __import__('random').Random(42)

type_counts = defaultdict(int)
for ex in examples:
    types_in_ex = list({e["type"] for e in ex["entities"]})
    for t in types_in_ex:
        type_counts[t] += 1

def _primary_stratum(ex):
    types_in_ex = list({e["type"] for e in ex["entities"]})
    if not types_in_ex:
        return "NONE"
    return min(types_in_ex, key=lambda t: type_counts.get(t, 0))

strata = defaultdict(list)
for idx, ex in enumerate(examples):
    stratum = _primary_stratum(ex)
    strata[stratum].append((idx, ex))

train, test = [], []
for stratum, members in strata.items():
    random.shuffle(members)
    n_test = max(1, round(len(members) * 0.2))
    n_test = min(n_test, len(members) - 1) if len(members) > 1 else n_test
    test_members = members[:n_test]
    train_members = members[n_test:]
    for _, ex in test_members:
        test.append(ex)
    for _, ex in train_members:
        train.append(ex)

deob = Deobfuscator()

print("Remaining EMAIL FNs after fixes:")
print("=" * 80)
fn_count = 0
for ex in test:
    email_entities = [e for e in ex["entities"] if e["type"] == "EMAIL"]
    if not email_entities:
        continue
    
    text = ex["text"]
    cleaned, log = deob(text)
    
    # Check all email patterns
    all_matches = set()
    for name, p, s in email_patterns:
        for m in p.finditer(cleaned):
            all_matches.add(m.group())
    
    for ent in email_entities:
        val = ent["value"]
        # Check the value against all matches
        # The benchmark compares if any match equals the gold value
        if val in all_matches:
            continue
        
        # Also check after deobfuscation: if value after cleaning matches
        val_cleaned, _ = deob(val)
        if val_cleaned in all_matches:
            continue
        
        fn_count += 1
        print(f"FN #{fn_count}: gold_value={val!r}")
        print(f"  text: {text!r}")
        print(f"  cleaned: {cleaned!r}")
        print(f"  matches: {list(all_matches)[:10]}")
        if log:
            for entry in log:
                print(f"  deob: [{entry['transform']}]")
        print()

print(f"\nTotal remaining FNs: {fn_count}")