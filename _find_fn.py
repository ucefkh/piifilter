"""Find which SSN examples in the held-out test set are FNs."""
import json
import re
import sys
import random

sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType
from piifilter.shared.deobfuscator import Deobfuscator
import json

# Replicate the benchmark's exact adapter logic
from piifilter.shared.deobfuscator import Deobfuscator

_DIRECT_MAP = {
    "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
    "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
    "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
    "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
    "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
    "DATE", "URL",
}

patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    type_map = {
        "SSN": "SOCIAL_SECURITY",
        "API_KEY": "API_KEY", "JWT": "JWT", "EMAIL": "EMAIL",
        "PHONE": "PHONE", "CREDIT_CARD": "CREDIT_CARD",
        "IP_ADDRESS": "IP_ADDRESS", "DATABASE_URL": "DATABASE_URL",
        "DOMAIN": "DOMAIN", "PRIVATE_URL": "PRIVATE_URL",
        "IBAN": "IBAN", "BANK_ACCOUNT": "BANK_ACCOUNT",
        "PASSPORT": "PASSPORT", "SSH_KEY": "SSH_KEY",
        "GPS": "GPS", "FILE_PATH": "FILE_PATH",
    }
    if type_name in _DIRECT_MAP:
        et_name = type_name
    else:
        et_name = type_map.get(type_name, type_name.upper())
    try:
        entity_type = EntityType(et_name)
    except ValueError:
        entity_type = EntityType("PERSON") if hasattr(EntityType, "PERSON") else EntityType("UNKNOWN")
    compiled = re.compile(raw_pattern, re.UNICODE)
    patterns.append((entity_type, compiled, score))

_deobfuscator = Deobfuscator()

def detect(text: str) -> list[dict]:
    if not text:
        return []
    cleaned, _log = _deobfuscator(text)
    entities = []
    seen_intervals = []
    for entity_type, pattern, score in patterns:
        for match in pattern.finditer(cleaned):
            start, end = match.start(), match.end()
            if start == end:
                continue
            contained = any(s <= start and end <= e for s, e in seen_intervals)
            if contained:
                continue
            new_seen = [(s, e) for s, e in seen_intervals if not (start <= s and e <= end)]
            if len(new_seen) != len(seen_intervals):
                subsumed_starts = {s for s, e in seen_intervals if start <= s and e <= end}
                entities = [e for e in entities if e["start"] not in subsumed_starts]
            seen_intervals = new_seen
            if entity_type == EntityType("CREDIT_CARD"):
                digits = "".join(c for c in match.group() if c.isdigit())
                if len(digits) >= 13 and not _luhn_valid(digits):
                    continue
            entities.append({
                "entity_type": entity_type.value,
                "value": match.group(),
                "start": start,
                "end": end,
                "score": score,
                "detector": "regex",
            })
            seen_intervals.append((start, end))
    entities.sort(key=lambda e: e["start"])
    return entities

def _luhn_valid(digits: str) -> bool:
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    for i in range(len(nums) - 2, -1, -2):
        nums[i] *= 2
        if nums[i] > 9:
            nums[i] -= 9
    return sum(nums) % 10 == 0

# Stratified train/test split (same as benchmark)
from collections import defaultdict

def stratified_train_test_split(examples, test_size=0.2, random_state=42):
    rng = random.Random(random_state)
    type_counts = defaultdict(int)
    for ex in examples:
        types_in_ex = list({e["type"] for e in ex["entities"]})
        for t in types_in_ex:
            type_counts[t] += 1

    def _primary_stratum(ex):
        types_in_ex = list({e["type"] for e in ex.entities})
        if not types_in_ex:
            return "NONE"
        return min(types_in_ex, key=lambda t: type_counts.get(t, 0))

    strata = defaultdict(list)
    for idx, ex in enumerate(examples):
        stratum = _primary_stratum(ex)
        strata[stratum].append((idx, ex))

    train: list = []
    test: list = []
    for stratum, members in strata.items():
        rng.shuffle(members)
        n_test = max(1, round(len(members) * test_size))
        n_test = min(n_test, len(members) - 1) if len(members) > 1 else n_test
        test_members = members[:n_test]
        train_members = members[n_test:]
        for _, ex in test_members:
            test.append(ex)
        for _, ex in train_members:
            train.append(ex)

    rng.shuffle(train)
    rng.shuffle(test)
    return train, test

data = json.load(open('benchmarks/data/pii_dataset_v2.json'))
examples = data["examples"]

# Build LabeledExample-like structure
class LabeledExample:
    def __init__(self, text, entities):
        self.text = text
        self.entities = entities

labeled = [LabeledExample(ex["text"], ex.get("entities", [])) for ex in examples]
train, test = stratified_train_test_split(labeled, test_size=0.2)

fn_ssn = []
for te in test:
    # Check ground truth SSNs
    ssn_gt = [e for e in te.entities if e["type"] == "SOCIAL_SECURITY"]
    if not ssn_gt:
        continue
    
    # Run detection
    results = detect(te.text)
    ssn_detected = [r for r in results if r["entity_type"] == "SOCIAL_SECURITY"]
    
    # Check each GT SSN
    for gt in ssn_gt:
        found = False
        for det in ssn_detected:
            if det["start"] <= gt["start"] and det["end"] >= gt["end"]:
                found = True
                break
        if not found:
            fn_ssn.append((te, gt, ssn_detected))

print(f"Total test examples: {len(test)}")
print(f"SSN examples: {len([t for t in test if any(e['type'] == 'SOCIAL_SECURITY' for e in t.entities)])}")
print(f"SSN FNs (after pattern changes): {len(fn_ssn)}")

for i, (te, gt, detected) in enumerate(fn_ssn):
    cleaned, _ = _deobfuscator(te.text)
    print(f"\nFN {i}:")
    print(f"  Text:    {repr(te.text[:120])}")
    print(f"  Cleaned: {repr(cleaned[:120])}")
    print(f"  GT val:  {repr(gt['value'])}")
    if detected:
        for d in detected:
            print(f"  Detected: {repr(d['value'])} at [{d['start']}:{d['end']}]")