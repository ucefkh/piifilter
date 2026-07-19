"""Debug EMAIL false negatives from held-out set."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "core" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "plugins" / "detector-regex" / "src"))

from piifilter.shared.deobfuscator import Deobfuscator

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"

DATA_PATH = DATA_DIR / "pii_dataset_v2.json"

raw = json.loads(DATA_PATH.read_text())
examples = raw["examples"]

# Filter to only EMAIL examples
email_examples = [ex for ex in examples if any(e["type"] == "EMAIL" for e in ex.get("entities", []))]
print(f"Total EMAIL examples: {len(email_examples)}")

# Use 20% held-out with seed 42 (same as benchmark)
random = __import__('random').Random(42)

# Same stratification logic as recall.py
from collections import defaultdict
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

# Current EMAIL pattern
pattern = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.UNICODE)
deob = Deobfuscator()

print(f"Test set size: {len(test)}")
print()

fn_count = 0
# Also test the pattern with deobfuscation
for ex in test:
    entities = [e for e in ex["entities"] if e["type"] == "EMAIL"]
    if not entities:
        continue
    
    text = ex["text"]
    cleaned, log = deob(text)
    
    # Check if original text matches
    orig_matches = [m.group() for m in pattern.finditer(text)]
    cleaned_matches = [m.group() for m in pattern.finditer(cleaned)]
    
    for ent in entities:
        val = ent["value"]
        found_in_orig = val in orig_matches
        found_in_cleaned = val in cleaned_matches
        
        if not found_in_orig and not found_in_cleaned:
            fn_count += 1
            offset_match = cleaned.find(val)
            print(f"FN #{fn_count}: value={val!r}")
            print(f"  Text: {text!r}")
            print(f"  Cleaned: {cleaned!r}")
            if offset_match >= 0:
                window = cleaned[max(0,offset_match-10):offset_match+len(val)+10]
                print(f"  Context around value in cleaned: ...{window!r}...")
            else:
                print(f"  Value NOT found in cleaned text at all!")
            print()

print(f"\nTotal EMAIL FN in held-out: {fn_count}")