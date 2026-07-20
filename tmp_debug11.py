"""Check URL-encoded phone match status."""
import sys
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from recall import load_dataset, make_regex_adapter, is_overlapping
import asyncio, math

async def check():
    adapter = make_regex_adapter()
    dataset = load_dataset()
    
    for idx, ex in enumerate(dataset):
        if '%2B1-555' in ex.text:
            results = await adapter.detect_fn(ex.text)
            print('Example %d:' % idx)
            print('  Text: %r' % ex.text)
            for r in results:
                print('  Detected: %s at (%d,%d) val=%r' % (r['entity_type'], r['start'], r['end'], r['value']))
            for e in ex.entities:
                val = ex.text[e['start']:e['end']]
                print('  Expected: %s at (%d,%d) val=%r' % (e['type'], e['start'], e['end'], val))
            
            for r in results:
                for e in ex.entities:
                    if r['entity_type'].upper() == e['type'].upper():
                        intxn = max(0, min(r['end'], e['end']) - max(r['start'], e['start']))
                        smallest = min(r['end'] - r['start'], e['end'] - e['start'])
                        iou = intxn / smallest if smallest > 0 else 0
                        ov = is_overlapping(r['start'], r['end'], e['start'], e['end'], 0.5)
                        print('    %s (%d,%d) vs %s (%d,%d): IoU=%.3f need>=0.5 -> %s' % (
                            r['value'][:15], r['start'], r['end'],
                            ex.text[e['start']:e['end']][:15], e['start'], e['end'],
                            iou, 'MATCH' if ov else 'NO MATCH'))

asyncio.run(check())