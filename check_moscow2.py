#!/usr/bin/env python3
"""Check what spans the detector returns for Moscow etc."""
import sys, asyncio
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def main():
    detector = RegexDetector()
    text = "GPS: lat: 55.7558, lng: 37.6173 (Moscow) and lat: 59.9343, lng: 30.3351 (SPB)"
    results = await detector.detect(text)
    city_results = [r for r in results if r.entity_type == 'CITY']
    for r in city_results:
        print(f"Detected CITY: '{r.text}' @ [{r.start}:{r.end}] in text:")
        print(f"  Span actual: '{text[r.start:r.end]}'")
    
    # Check original offsets
    print(f"\nOriginal 'Moscow' at: {text.index('Moscow')}")

if __name__ == '__main__':
    asyncio.run(main())