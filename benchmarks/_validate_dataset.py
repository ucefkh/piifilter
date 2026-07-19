"""Quick dataset validation."""
import json
from pathlib import Path

data = json.loads(Path("benchmarks/data/pii_dataset.json").read_text())
examples = data["examples"]

print(f"Examples: {len(examples)}")

total = sum(len(ex.get("entities", [])) for ex in examples)
print(f"Total entities: {total}")

# Entity types
types = set()
for ex in examples:
    for ent in ex.get("entities", []):
        types.add(ent["type"])
print(f"Entity types ({len(types)}): {sorted(types)}")

# Validate positions
for i, ex in enumerate(examples):
    text = ex["text"]
    for j, ent in enumerate(ex.get("entities", [])):
        start, end = ent["start"], ent["end"]
        assert start <= end, f"#{i} ent#{j}: start > end"
        assert start >= 0, f"#{i} ent#{j}: negative start"
        assert end <= len(text), f"#{i} ent#{j}: end {end} > len {len(text)}"
        actual = text[start:end]
        expected = ent["value"]
        if actual != expected:
            print(f"WARN #{i} ent#{j}: value mismatch |{actual}| != |{expected}|")
            # fix inline for next pass
            ent["value"] = actual

# Check for duplicates
texts = [ex["text"] for ex in examples]
dupes = len(texts) - len(set(texts))
if dupes:
    print(f"WARN: {dupes} duplicate texts")
else:
    print("No duplicate texts")

print("Validation done")