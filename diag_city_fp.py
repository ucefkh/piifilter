#!/usr/bin/env python3
"""Diagnose CITY false positives using async."""
import sys, asyncio, json, re
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter_detector_regex.detector import RegexDetector
from piifilter_detector_regex.patterns import PATTERN_DEFS

async def main():
    with open('benchmarks/data/pii_dataset.json') as f:
        dataset = json.load(f)
    examples = dataset['examples']
    
    detector = RegexDetector()
    
    fp_items = []
    for ex in examples:
        text = ex['text']
        entities = ex['entities']
        results = await detector.detect(text)
        city_results = [r for r in results if r.entity_type == 'CITY']
        city_labels = [text[e['start']:e['end']] for e in entities if e.get('type') == 'CITY']
        
        if not city_results:
            continue
        
        for r in city_results:
            val = r.text
            if val not in city_labels:
                fp_items.append((val, text, r.raw_score))
    
    print(f"=== TOTAL CITY FPs: {len(fp_items)} ===")
    for val, ctx, conf in fp_items[:40]:
        print(f"\nFP: '{val}' (conf={conf})")
        print(f"  Context: {ctx[:120]}")
        
        # Find which pattern matched
        for typ, pat, pconf in [(t,p,c) for t,p,c in PATTERN_DEFS if t == 'CITY']:
            m = re.search(pat, ctx)
            if m and val in m.group():
                print(f"  Pattern (conf={pconf}): {pat[:60]}...")
                break

if __name__ == '__main__':
    asyncio.run(main())