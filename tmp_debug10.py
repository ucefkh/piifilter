"""Debug example 50 with adapter."""
import sys, asyncio, json
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter, is_overlapping

async def check():
    adapter = make_regex_adapter()
    dataset = load_dataset()
    
    ex = dataset[50]
    print("Text: %r" % ex.text)
    
    results = await adapter.detect_fn(ex.text)
    phone_results = [r for r in results if r['entity_type'] == 'PHONE']
    print("\nPhone results from adapter:")
    for r in phone_results:
        print("  score=%s: %r at (%d,%d)" % (r['score'], r['value'], r['start'], r['end']))
    
    expected = [e for e in ex.entities if e['type'] == 'PHONE']
    print("\nExpected phones:")
    for e in expected:
        print("  %r at (%d,%d)" % (ex.text[e['start']:e['end']], e['start'], e['end']))
    
    # Manual matching
    matched_exp = [False] * len(expected)
    matched_det = [False] * len(phone_results)
    for di, r in enumerate(phone_results):
        for ei, ee in enumerate(expected):
            if matched_exp[ei]:
                continue
            if r['entity_type'].upper() == ee['type'].upper():
                if is_overlapping(r['start'], r['end'], ee['start'], ee['end'], 0.5):
                    matched_exp[ei] = True
                    matched_det[di] = True
                    print("\n  Match: det(%r) <-> exp(%r)" % (r['value'], ex.text[ee['start']:ee['end']]))
                    print("    det(%d,%d) exp(%d,%d)" % (r['start'], r['end'], ee['start'], ee['end']))
                    break
    
    print("\nMatched expected: %s" % matched_exp)
    print("Matched detected: %s" % matched_det)

asyncio.run(check())