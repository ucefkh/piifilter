"""Debug example 50 matching in detail."""
import sys
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter, is_overlapping
import asyncio

async def check():
    adapter = make_regex_adapter()
    dataset = load_dataset()
    
    ex = dataset[50]
    print("Text: %r" % ex.text)
    print()
    
    results = await adapter.detect_fn(ex.text)
    phone_det = [r for r in results if r['entity_type'] == 'PHONE']
    phone_exp = [e for e in ex.entities if e['type'] == 'PHONE']
    
    print("Expected phones:")
    for ee in phone_exp:
        val = ex.text[ee['start']:ee['end']]
        print("  %r at (%d,%d)" % (val, ee['start'], ee['end']))
    print()
    
    print("Detected phones:")
    for r in phone_det:
        print("  score=%s %r at (%d,%d)" % (r['score'], r['value'], r['start'], r['end']))
    print()
    
    # Check match pairs
    matched_exp = [False] * len(phone_exp)
    matched_det = [False] * len(phone_det)
    
    for di, r in enumerate(phone_det):
        for ei, ee in enumerate(phone_exp):
            if matched_exp[ei]:
                continue
            if r['entity_type'].upper() == ee['type'].upper():
                ov = is_overlapping(r['start'], r['end'], ee['start'], ee['end'], 0.5)
                inter = max(0, min(r['end'], ee['end']) - max(r['start'], ee['start']))
                small = min(r['end'] - r['start'], ee['end'] - ee['start'])
                iou = inter / small if small > 0 else 0
                if ov:
                    matched_exp[ei] = True
                    matched_det[di] = True
                    print("MATCH: det(%s) vs exp(%s): IoU=%.3f" % (r['value'][:15], ex.text[ee['start']:ee['end']][:15], iou))
                    break
    
    print("\nUnmatched expected:")
    for ei, matched in enumerate(matched_exp):
        if not matched:
            ee = phone_exp[ei]
            val = ex.text[ee['start']:ee['end']]
            print("  %r at (%d,%d)" % (val, ee['start'], ee['end']))
    
    print("\nUnmatched detected:")
    for di, matched in enumerate(matched_det):
        if not matched:
            r = phone_det[di]
            print("  score=%s %r at (%d,%d)" % (r['score'], r['value'], r['start'], r['end']))

asyncio.run(check())