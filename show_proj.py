#!/usr/bin/env python3
import json
data = json.load(open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/pii_dataset.json'))
examples = data['examples']
for e in examples:
    text = e.get('text','')
    for ent in e.get('entities',[]):
        if ent.get('type')=='PROJECT_NAME':
            start, end = ent.get('start',0), ent.get('end',len(text))
            val = text[start:end]
            print(f"  text[{start}:{end}] = {repr(val)}")
            print(f"  context before: {repr(text[max(0,start-20):start])}")
            print(f"  context after:  {repr(text[end:end+20])}")
            print()