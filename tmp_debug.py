"""Debug PHONE FPs and FNs in benchmark."""
import sys, json, asyncio
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter

async def check():
    dataset = load_dataset()
    adapter = make_regex_adapter()
    fps = []
    fns = []
    
    for ex in dataset:
        results = await adapter.detect_fn(ex.text)
        detected_phone = [r for r in results if r['entity_type'] == 'PHONE']
        expected_phone = [e for e in ex.entities if e['type'] == 'PHONE']
        
        # Check FPs
        for r in detected_phone:
            val_digits = ''.join(c for c in r['value'] if c.isdigit())
            is_real = False
            for e in expected_phone:
                exp_digits = ''.join(c for c in ex.text[e['start']:e['end']] if c.isdigit())
                if val_digits == exp_digits:
                    is_real = True
                    break
            if not is_real:
                fps.append((ex.text, r['value'], r['score']))
        
        # Check FNs
        for e in expected_phone:
            exp_text = ex.text[e['start']:e['end']]
            exp_digits = ''.join(c for c in exp_text if c.isdigit())
            is_found = False
            for r in detected_phone:
                val_digits = ''.join(c for c in r['value'] if c.isdigit())
                if val_digits == exp_digits:
                    is_found = True
                    break
            if not is_found:
                fns.append((ex.text, exp_text, e))
    
    print(f"\n=== PHONE: {len(fps)} FPs ===")
    for text, val, score in fps:
        print(f"  FP score={score}: {val!r} in {text[:120]!r}")
    print(f"\n=== PHONE: {len(fns)} FNs ===")
    for text, val, ent in fns:
        print(f"  FN: {val!r} type={ent} in {text[:120]!r}")

asyncio.run(check())