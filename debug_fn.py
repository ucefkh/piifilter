"""Debug which PERSON entities are being false-negatived by the arbitrator."""
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
    
    total_fn = 0
    total_presidio_caught = 0
    total_presidio_missed = 0
    
    for idx, ex in enumerate(examples):
        text = ex.text
        expected_entities = ex.entities
        
        person_expected = [e for e in expected_entities if e['type'].upper() == 'PERSON']
        if not person_expected:
            continue
        
        presidio_raw = await pipe.detect_fn(text)
        presidio_persons = [d for d in presidio_raw if d.get('entity_type') == 'PERSON']
        
        arb_results = await arb.detect_fn(text)
        arb_persons = [d for d in arb_results if d.get('entity_type') == 'PERSON']
        
        for pe in person_expected:
            pe_val = pe['value'].lower()
            matched_arb = any(pe_val == d.get('value', '').lower() for d in arb_persons)
            matched_presidio = any(pe_val == d.get('value', '').lower() for d in presidio_persons)
            
            if not matched_arb:
                total_fn += 1
                if matched_presidio:
                    total_presidio_caught += 1
                    pd = [d for d in presidio_persons if d.get('value','').lower() == pe_val]
                    score = pd[0].get('score', 'N/A') if pd else 'N/A'
                    print(f'FN: "{pe["value"]}" (score={score}) in: {text[:120]}')
                else:
                    total_presidio_missed += 1
                    print(f'FN-no-presidio: "{pe["value"]}" in: {text[:120]}')
    
    print(f'\nSummary:')
    print(f'  PERSON FN total: {total_fn}')
    print(f'  Presidio caught but arbitration dropped: {total_presidio_caught}')
    print(f'  Presidio also missed: {total_presidio_missed}')

asyncio.run(analyze())