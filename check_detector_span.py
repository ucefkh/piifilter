#!/usr/bin/env python3
"""Examine what the benchmark receives from the detector."""
import sys, asyncio, json
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def main():
    detector = RegexDetector()
    
    with open('benchmarks/data/pii_dataset.json') as f:
        dataset = json.load(f)
    
    for ex in dataset['examples'][:2]:
        text = ex['text']
        print(f"\n=== Example ===")
        print(f"Text: {text}")
        print(f"Entities: {[(e['type'], text[e['start']:e['end']], e['start'], e['end']) for e in ex['entities']]}")
        
        results = await detector.detect(text)
        for r in results:
            d = r.to_dict()
            actual = text[d['start']:d['end']] if d['start'] < len(text) else '?'
            print(f"  Detected: type={d['type']}, value='{d['text']}', start={d['start']}, end={d['end']}, actual_text='{actual}'")

if __name__ == '__main__':
    asyncio.run(main())