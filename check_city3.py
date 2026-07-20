#!/usr/bin/env python3
"""Load benchmark results and examine CITY FPs/FNs in detail."""
import sys, asyncio, json
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def main():
    with open('benchmarks/data/pii_dataset.json') as f:
        dataset = json.load(f)
    examples = dataset['examples']
    
    detector = RegexDetector()
    
    for ex in examples:
        text = ex['text']
        entities = ex['entities']
        results = await detector.detect(text)
        
        city_results = [r for r in results if r.entity_type == 'CITY']
        city_labels = [{'value': text[e['start']:e['end']], 'start': e['start'], 'end': e['end']} 
                       for e in entities if e.get('type') == 'CITY']
        
        # Use benchmark's span-matching logic: exact span match
        for r in city_results:
            matched_label = any(r.start == l['start'] and r.end == l['end'] for l in city_labels)
            if not matched_label:
                print(f"FP: '{r.text}' @ [{r.start}:{r.end}] (conf={r.raw_score}) in: {text[:120]}")
        
        for l in city_labels:
            matched_det = any(r.start == l['start'] and r.end == l['end'] for r in city_results)
            if not matched_det:
                print(f"FN: '{l['value']}' @ [{l['start']}:{l['end']}] in: {text[:120]}")

if __name__ == '__main__':
    asyncio.run(main())