"""Find the PHONE FP that maps to NONE."""
import sys, asyncio
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter, is_overlapping

async def check():
    adapter = make_regex_adapter()
    dataset = load_dataset()
    
    for ex in dataset:
        results = await adapter.detect_fn(ex.text)
        for r in results:
            if r['entity_type'] == 'PHONE':
                overlaps = False
                for ee in ex.entities:
                    if is_overlapping(r['start'], r['end'], ee['start'], ee['end'], 0.25):
                        overlaps = True
                        if ee['type'] != 'PHONE':
                            val = ex.text[ee['start']:ee['end']]
                            print("PHONE FP (diff type): %r at (%d,%d)" % (r['value'], r['start'], r['end']))
                            print("  Overlaps with %s: %r" % (ee['type'], val))
                            print("  Text: %r" % ex.text[:160])
                            print()
                        break
                if not overlaps:
                    print("PHONE FP (NONE): %r at (%d,%d) score=%s" % (r['value'], r['start'], r['end'], r['score']))
                    print("  Text: %r" % ex.text[:160])
                    print()

asyncio.run(check())