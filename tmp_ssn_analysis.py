#!/usr/bin/env python3
"""Investigate SSN area ranges and real SSA data."""
# SSA area numbers: https://www.ssa.gov/employer/stateweb.htm
# Areas 001-772 are allocated. 773–899 are unused but could be allocated later.
# From SSA: "Not every number in the range 001-772 is an SSN"
# Areas above 899 remain unused.

# Valid SSA areas are 001-772 inclusive (with some gaps for individual states)
# Areas 773-899 are "not yet issued" but reserved for future use
# Areas 900-999 are NEVER valid SSN areas
# Area 666 is NEVER valid

# Key question: which of our test SSN areas fall in 773-899 vs 900-999?
invalid_areas = set()
area_900_plus = set()
area_773_899 = set()

for area in range(900, 1000):
    area_900_plus.add(area)

for area in range(773, 900):
    area_773_899.add(area)

# SSNs from the dataset with area_ok=False
problem_ssns = [
    ("987-65-4321", 987),
    ("996.29.8532", 996),
    ("911683710", 911),
    ("996.78.0826", 996),
    ("935-41-5892", 935),
    ("908-12-2681", 908),
    ("934-83-5862", 934),
    ("934-43-6958", 934),
    ("934 83 5862 (segmented)", 934),
    ("9284-50-550", 928),
]

print("Problem SSNs:")
for label, area in problem_ssns:
    if area >= 900:
        print(f"  {label:40s} area={area} → 900+ range, NEVER valid SSN area")
    elif area >= 773:
        print(f"  {label:40s} area={area} → 773-899 range, RESERVED but could be valid")
    else:
        print(f"  {label:40s} area={area} → other invalid area")

# Also check: what about SSNs with area 000, 666?
print("\nCurrent SSNValidator rejects:")
print("  area == 000: correct - never valid")
print("  area == 666: correct - never valid")  
print("  area >= 900: correct - never valid")
print("\nProposed relaxation (for structural pass, not final validation):")
print("  area >= 773 but < 900: still reject — SSA hasn't issued these")
print("  area >= 900: NEVER valid — keep rejecting")
print()
print("However, for RECALL purposes we need to detect ALL 9-digit SSN-like patterns")
print("regardless of area — precision is handled by confidence scoring downstream.")

# Let's count how many SSNs in v2 dataset are rejected due to area
import json
with open("/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/pii_dataset_v2.json") as f:
    data = json.load(f)
if isinstance(data, dict):
    examples = data.get("examples", [])
else:
    examples = data

area_rejects_900 = 0
area_rejects_666 = 0
area_rejects_000 = 0
area_rejects_none = 0
total_real_ssns = 0  # non-obfuscated

for ex in examples:
    if isinstance(ex, str):
        continue
    for e in ex.get("entities", []):
        if e["type"] == "SOCIAL_SECURITY":
            # Skip masked/obfuscated ones  
            span = e["value"] if "value" in e else ex["text"][e["start"]:e["end"]]
            if "X" in span or "*" in span or "•" in span or len(re.sub(r'[^0-9]', '', span)) != 9:
                continue
            text = ex["text"]
            span_text = text[e["start"]:e["end"]]
            digits = re.sub(r'[^0-9]', '', span_text)
            if len(digits) != 9:
                continue
            total_real_ssns += 1
            area = int(digits[:3])
            if area == 0:
                area_rejects_000 += 1
            elif area == 666:
                area_rejects_666 += 1
            elif area >= 900:
                area_rejects_900 += 1
            else:
                area_rejects_none += 1

print(f"\nDataset SSN analysis (non-obfuscated, 9-digit):")
print(f"  Total real SSNs: {total_real_ssns}")
print(f"  Rejected area=000: {area_rejects_000}")
print(f"  Rejected area=666: {area_rejects_666}")
print(f"  Rejected area>=900: {area_rejects_900}")
print(f"  Passed: {area_rejects_none}")