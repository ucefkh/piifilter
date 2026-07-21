"""Debug PERSON FPs in pipeline-arbitration"""
import json
import sys
from pathlib import Path

sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-presidio/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/core/src')

from benchmarks.recall import (
    LabeledExample, make_arbitration_adapter,
    DetectorAdapter, make_pipeline_adapter
)

DATA_DIR = Path('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data')
with open(DATA_DIR / 'ood_corpus_v1.json') as f:
    data = json.load(f)

examples = []
for ex in data['examples']:
    entities = []
    for e in ex.get('entities', []):
        entities.append({
            'type': e['type'],
            'value': e['value'],
            'start': e.get('start', 0),
            'end': e.get('end', 0),
        })
    examples.append(LabeledExample(text=ex['text'], entities=entities))

import asyncio

async def analyze():
    pipe = await make_pipeline_adapter()
    arb = make_arbitration_adapter(pipe)
    
    total_fp = 0
    
    for idx, ex in enumerate(examples):
        text = ex.text
        expected_types = {e['type'].upper() for e in ex.entities}
        expected_values = {(e['value'].lower(), e['start'], e['end']) for e in ex.entities}
        
        if 'PERSON' in expected_types:
            continue  # Skip PERSON expected — focus on FPs
        
        arb_results = await arb.detect_fn(text)
        arb_persons = [d for d in arb_results if d.get('entity_type') == 'PERSON']
        
        for d in arb_persons:
            val = d.get('value', '')
            start = d.get('start', 0)
            end = d.get('end', 0)
            # Check if it really matches a ground-truth PERSON
            is_tp = any(
                val.lower() == ev[0] and start >= ev[1] and end <= ev[2]
                for ev in expected_values if ev[0] == val.lower()
            )
            if not is_tp:
                total_fp += 1
                detector = d.get('detector', '?')
                score = d.get('score', '?')
                print(f'FP {total_fp}: "{val}" (det={detector}, score={score}) in: {text[:150]}')
    
    print(f'\nTotal PERSON FPs: {total_fp}')

asyncio.run(analyze())