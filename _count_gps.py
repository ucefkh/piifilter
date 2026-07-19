#!/usr/bin/env python3
"""Count all GPS entities and check each."""
import json

data = json.load(open('benchmarks/data/pii_dataset.json'))
gps_count = 0
gps_examples = []
for ex in data['examples']:
    for e in ex['entities']:
        if e['type'] == 'GPS':
            gps_count += 1
            gps_examples.append((ex['text'][:100], e))

print(f"Total GPS entities: {gps_count}")
for text, e in gps_examples:
    context_start = max(0, e['start'] - 30)
    context_end = min(len(text), e['end'] + 30)
    ctx = text[context_start:context_end]
    if context_start > 0: ctx = "..." + ctx
    if context_end < len(text): ctx = ctx + "..."
    print(f"  {repr(e['value'])} at [{e['start']}:{e['end']}] in: {repr(ctx)}")