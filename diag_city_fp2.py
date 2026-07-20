#!/usr/bin/env python3
"""Check what's labeled as CITY in the dataset."""
import sys, asyncio, json
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def main():
    with open('benchmarks/data/pii_dataset.json') as f:
        dataset = json.load(f)
    examples = dataset['examples']
    
    detector = RegexDetector()
    
    # Print every example that has or should have CITY
    for ex in examples:
        text = ex['text']
        entities = ex['entities']
        
        city_labels = [text[e['start']:e['end']] for e in entities if e.get('type') == 'CITY']
        
        results = await detector.detect(text)
        city_detections = [r.text for r in results if r.entity_type == 'CITY']
        
        if city_labels or city_detections:
            print(f"\n---")
            print(f"Text: {text[:150]}")
            print(f"Labeled CITY: {city_labels}")
            print(f"Detected CITY: {city_detections}")

if __name__ == '__main__':
    asyncio.run(main())