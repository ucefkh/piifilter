import json
from collections import Counter

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

examples = data["examples"]
types = Counter()
for item in examples:
    for ent in item["entities"]:
        types[ent["type"]] += 1

print('Entity type distribution:')
for t, c in sorted(types.items(), key=lambda x: -x[1]):
    print(f'  {t}: {c}')

# Sample examples of the target low-recall types
targets = ['DATE', 'URL', 'CUSTOMER_NAME', 'EMPLOYEE_NAME', 'IBAN', 'SSH_KEY', 'PROJECT_NAME', 'PASSPORT', 'PRIVATE_URL', 'BANK_ACCOUNT']
for target in targets:
    print(f'\n=== {target} examples (first 5) ===')
    count = 0
    for item in examples:
        for ent in item["entities"]:
            if ent["type"] == target:
                full_text = item["text"]
                val = ent["value"]
                ctx_start = max(0, ent["start"] - 30)
                ctx_end = min(len(full_text), ent["end"] + 40)
                context = full_text[ctx_start:ctx_end]
                print(f'  value={repr(val):<60} ctx={repr(context[:100])}')
                count += 1
                if count >= 5:
                    break
        if count >= 5:
            break