"""Debug example 50."""
import sys, asyncio, json
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset
from piifilter_detector_regex.detector import RegexDetector

async def check():
    det = RegexDetector()
    dataset = load_dataset()
    
    ex = dataset[50]
    print("Text: %r" % ex.text)
    print("Expected entities:")
    for ee in ex.entities:
        print("  %s: %r at (%d,%d)" % (ee['type'], ex.text[ee['start']:ee['end']], ee['start'], ee['end']))
    print()
    
    results = await det.detect(ex.text)
    print("Detected entities:")
    for r in results:
        print("  %s (score=%s): %r at (%d,%d)" % (r['type'], r['score'], r['text'], r['start'], r['end']))
    
    # Check phones only
    phones = [r for r in results if r['type'] == 'PHONE']
    print("\nPhone entities:")
    for r in phones:
        print("  score=%s: %r at (%d,%d)" % (r['score'], r['text'], r['start'], r['end']))

asyncio.run(check())