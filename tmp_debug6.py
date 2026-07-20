"""Debug why benchmark says False for URL-encoded phone."""
import sys, asyncio, json
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter, is_overlapping

async def check():
    adapter = make_regex_adapter()
    
    text = 'URL-encoded phone: %2B1-555-123-4567'
    results = await adapter.detect_fn(text)
    print(f"Results from adapter: {json.dumps(results, indent=2)}")
    
    # Check against expected
    dataset = load_dataset()
    for ex in dataset:
        if '%2B1-555' in ex.text:
            expected = ex.entities[0]
            print(f"\nExpected: {json.dumps(expected)}")
            
            for r in results:
                det_type = r['entity_type'].upper()
                exp_type = expected['type'].upper()
                print(f"  Type match: {det_type} == {exp_type}: {det_type == exp_type}")
                
                intxn = max(0, min(r['end'], expected['end']) - max(r['start'], expected['start']))
                smallest = min(r['end'] - r['start'], expected['end'] - expected['start'])
                overlap = intxn / smallest if smallest > 0 else 0
                print(f"  Span overlap: det({r['start']},{r['end']}) vs exp({expected['start']},{expected['end']})")
                print(f"    intersection={intxn}, smallest={smallest}, IoU={overlap}")
                
                span_match = is_overlapping(r['start'], r['end'], expected['start'], expected['end'], 0.5)
                print(f"    is_overlapping result: {span_match}")

asyncio.run(check())