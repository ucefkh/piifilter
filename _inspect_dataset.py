import json

with open('benchmarks/data/pii_dataset_v2.json') as f:
    data = json.load(f)

if isinstance(data, dict):
    print('Keys:', list(data.keys()))
    if 'entries' in data:
        items = data['entries']
    elif 'data' in data:
        items = data['data']
    else:
        items = []
elif isinstance(data, list):
    items = data

print(f'Total items: {len(items)}')

# Look for any IP-related entries
ip_items = [item for item in items if 'IP' in str(item.get('entity_type', '')) or 'ip' in str(item.get('entity_type', '')).lower()]
print(f'IP items: {len(ip_items)}')
for item in ip_items[:20]:
    print(json.dumps(item, indent=2))

# Also check unique entity types
entity_types = set()
for item in items:
    et = item.get('entity_type', item.get('label', item.get('type', '???')))
    entity_types.add(et)
print('Entity types:', sorted(entity_types))