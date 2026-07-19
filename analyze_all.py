#!/usr/bin/env python3
"""Show all DATE and SSH_KEY examples to build comprehensive patterns."""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

with open(PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset_v2.json") as f:
    data = json.load(f)

# Show ALL DATE examples
print("=== ALL DATE EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "DATE" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 15)
            ctx_end = min(len(item["text"]), ent["end"] + 15)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {ent['value']:<25}  {repr(context[:80])}")

print(f"\nTotal unique DATE values: {len(seen)}")

# Show ALL URL examples
print("\n=== ALL URL EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "URL" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 10)
            ctx_end = min(len(item["text"]), ent["end"] + 10)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:80]}")

# Show ALL SSH_KEY examples
print("\n=== ALL SSH_KEY EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "SSH_KEY" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 15)
            ctx_end = min(len(item["text"]), ent["end"] + 15)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:100]}")

# Show ALL IBAN examples
print("\n=== ALL IBAN EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "IBAN" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 15)
            ctx_end = min(len(item["text"]), ent["end"] + 15)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:100]}")

# Show ALL PROJECT_NAME examples
print("\n=== ALL PROJECT_NAME EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "PROJECT_NAME" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 15)
            ctx_end = min(len(item["text"]), ent["end"] + 15)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:100]}")

# Show ALL CUSTOMER_NAME examples
print("\n=== ALL CUSTOMER_NAME EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "CUSTOMER_NAME" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 20)
            ctx_end = min(len(item["text"]), ent["end"] + 20)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:100]}")

# Show ALL EMPLOYEE_NAME examples
print("\n=== ALL EMPLOYEE_NAME EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "EMPLOYEE_NAME" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 20)
            ctx_end = min(len(item["text"]), ent["end"] + 20)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:100]}")

# Show ALL PRIVATE_URL examples  
print("\n=== ALL PRIVATE_URL EXAMPLES ===")
seen = set()
for item in data["examples"]:
    for ent in item["entities"]:
        if ent["type"] == "PRIVATE_URL" and ent["value"] not in seen:
            seen.add(ent["value"])
            ctx_start = max(0, ent["start"] - 10)
            ctx_end = min(len(item["text"]), ent["end"] + 10)
            context = item["text"][ctx_start:ctx_end]
            print(f"  {context[:100]}")