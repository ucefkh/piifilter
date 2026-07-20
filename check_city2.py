#!/usr/bin/env python3
"""Check remaining CITY FP/FN after fixes."""
import sys, asyncio, json
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def main():
    with open('benchmarks/data/pii_dataset.json') as f:
        dataset = json.load(f)
    examples = dataset['examples']
    
    detector = RegexDetector()
    
    fps = []
    fns = []
    for ex in examples:
        text = ex['text']
        entities = ex['entities']
        results = await detector.detect(text)
        city_results = [r for r in results if r.entity_type == 'CITY']
        city_labels = [text[e['start']:e['end']] for e in entities if e.get('type') == 'CITY']
        
        # FPs: detected but not labeled
        city_detected_vals = [r.text for r in city_results]
        for r in city_results:
            if r.text not in city_labels:
                fps.append((r.text, text[:120], r.raw_score))
        
        # FNs: labeled but not detected
        for lbl in city_labels:
            if lbl not in city_detected_vals:
                # Check for span overlap (if pattern matched but with slightly different span)
                overlap = False
                for r in city_results:
                    if lbl in r.text or r.text in lbl:
                        overlap = True
                        break
                if not overlap:
                    fns.append((lbl, text[:120]))
    
    print(f"=== CITY FPs: {len(fps)} ===")
    for val, ctx, conf in fps:
        print(f"  '{val}' (conf={conf}): {ctx}")
    
    print(f"\n=== CITY FNs: {len(fns)} ===")
    for val, ctx in fns:
        print(f"  '{val}': {ctx}")

if __name__ == '__main__':
    asyncio.run(main())