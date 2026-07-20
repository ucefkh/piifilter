"""Final check of PHONE metrics."""
import sys
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter, is_overlapping
import asyncio

async def check():
    adapter = make_regex_adapter()
    dataset = load_dataset()
    
    fps = []
    fns = []
    
    for idx, ex in enumerate(dataset):
        results = await adapter.detect_fn(ex.text)
        phone_det = [r for r in results if r['entity_type'] == 'PHONE']
        phone_exp = [e for e in ex.entities if e['type'] == 'PHONE']
        
        matched_exp = [False] * len(phone_exp)
        matched_det = [False] * len(phone_det)
        
        for di, r in enumerate(phone_det):
            for ei, ee in enumerate(phone_exp):
                if matched_exp[ei]:
                    continue
                if r['entity_type'].upper() == ee['type'].upper():
                    if is_overlapping(r['start'], r['end'], ee['start'], ee['end'], 0.5):
                        matched_exp[ei] = True
                        matched_det[di] = True
                        break
        
        for ei, matched in enumerate(matched_exp):
            if not matched:
                ee = phone_exp[ei]
                val = ex.text[ee['start']:ee['end']]
                fns.append((idx, val, ee['start'], ee['end'], ex.text[:120]))
        
        for di, matched in enumerate(matched_det):
            if not matched:
                r = phone_det[di]
                fps.append((idx, r['value'], r['start'], r['end'], r['score'], ex.text[:120]))
    
    print("=== PHONE FNs ===")
    for idx, val, s, e, txt in fns:
        print("  Example %d: %r at (%d,%d)" % (idx, val, s, e))
        print("    %r" % txt)
    
    print("\n=== PHONE FPs ===")
    for idx, val, s, e, score, txt in fps:
        print("  Example %d: score=%s %r at (%d,%d)" % (idx, score, val, s, e))
        print("    %r" % txt)
    
    print("\nTotal: FN=%d, FP=%d" % (len(fns), len(fps)))

asyncio.run(check())