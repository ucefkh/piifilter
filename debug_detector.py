"""Debug PERSON false positives — find which detector produces them."""
import sys
import asyncio
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter_detector_regex.detector import RegexDetector

async def main():
    detector = RegexDetector()
    texts = [
        "Uma Carter (uma.carter@temp-services.co.uk) works at Aviato",
        "Sofia King (sofia.king@bigpharma.com) works at Oceanic Airlines",
        "Zack Jackson (zack.jackson@mail.company.io) works at Tyrell Corp",
        "Aaron Lee (aaron.lee@temp-services.co.uk) works at Dunder Mifflin",
    ]
    
    for text in texts:
        results = await detector.detect(text)
        person_results = [r for r in results if r.entity_type == 'PERSON']
        if person_results:
            for r in person_results:
                print(f"  TEXT: {text}")
                print(f"  REGEX PERSON: '{text[r.start:r.end]}' at [{r.start}:{r.end}] conf={r.confidence}")
                print()
        else:
            print(f"  TEXT: {text}")
            print(f"  REGEX: no PERSON detected")
            print()

asyncio.run(main())