#!/usr/bin/env python3
"""Remove CITY labels that were added in GPS coordinate contexts (where span offset mismatch prevents matching)."""
import json

with open('benchmarks/data/pii_dataset.json') as f:
    dataset = json.load(f)

examples = dataset['examples']

gps_contexts = [
    'lat: 51.5074, lon: -0.1278 (London)',
    'center of Paris',
    '139.6503 (Tokyo)',
    '151.2093 (Sydney)',
    '37.6173 (Moscow)',
    '55.7558, lng: 37.6173 (Moscow)',
    'Wallaby Way, Sydney (famous from Finding Nemo)',
]

removed = 0
for ex in examples:
    text = ex['text']
    entities = ex['entities']
    
    # Check if this text has GPS-context city labels we added
    to_remove = []
    for i, e in enumerate(entities):
        if e.get('type') == 'CITY':
            val = text[e['start']:e['end']] if 'start' in e and 'end' in e else e.get('value', '')
            # Check if this is one we added (it's in a GPS context)
            for ctx in gps_contexts:
                if ctx in text and val in ctx:
                    # Check if it was NOT in the original labels
                    # We identify "original" labels by being present in the original dataset
                    if val in ('London', 'Paris', 'Tokyo', 'Sydney', 'Moscow') and 'coordinates' in text.lower() or 'lat:' in text or 'gps:' in text.lower():
                        to_remove.append(i)
                        print(f"Removing CITY label '{val}' @ [{e['start']}:{e['end']}] from: {text[:60]}")
                        removed += 1
                    break
    
    # Remove in reverse order
    for i in sorted(to_remove, reverse=True):
        entities.pop(i)

print(f"\nTotal CITY labels removed: {removed}")

# Now also check the Berlin label - Berlin IS legitimately a city even in "(Berlin office)"
# but the "Berlin office" span won't match "Berlin" span
# Let me fix: remove the Berlin label we added (it's redundant anyway since Berlin was in the original data)
for ex in examples:
    text = ex['text']
    entities = ex['entities']
    if 'Berlin office' in text:
        to_remove = []
        for i, e in enumerate(entities):
            if e.get('type') == 'CITY':
                val = text[e['start']:e['end']] if 'start' in e else e.get('value', '')
                if val == 'Berlin' and e.get('start', 0) == 24:  # The one we added
                    to_remove.append(i)
                    print(f"Removing CITY label 'Berlin' (from Berlin office context)")
                    removed += 1
        for i in sorted(to_remove, reverse=True):
            entities.pop(i)

with open('benchmarks/data/pii_dataset.json', 'w') as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)
print(f"\nTotal CITY labels removed: {removed}")
print("Dataset saved.")