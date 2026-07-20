"""Debug why phone fix didn't change metrics."""
import sys, asyncio
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def check():
    det = RegexDetector()
    
    # Test the URL-encoded phone case
    text = 'URL-encoded phone: %2B1-555-123-4567'
    print(f"Text: {text!r}")
    results = await det.detect(text)
    print(f"Entities: {len(results)}")
    for r in results:
        print(f"  type={r['type']} score={r['score']} value={r['text']!r} span=({r['start']},{r['end']})")
    
    print()
    
    # Check what happens with full dataset
    from recall import load_dataset
    dataset = load_dataset()
    
    phone_tps = 0
    phone_fps = 0
    phone_fns = 0
    
    for ex in dataset:
        results = await det.detect(ex.text)
        detected_phone = [r for r in results if r['type'] == 'PHONE']
        expected_phone = [e for e in ex.entities if e['type'] == 'PHONE']
        
        matched_expected = [False] * len(expected_phone)
        matched_detected = [False] * len(detected_phone)
        
        for di, r in enumerate(detected_phone):
            val_digits = ''.join(c for c in r['text'] if c.isdigit())
            for ei, ee in enumerate(expected_phone):
                if matched_expected[ei]:
                    continue
                exp_digits = ''.join(c for c in ex.text[ee['start']:ee['end']] if c.isdigit())
                if val_digits == exp_digits:
                    matched_expected[ei] = True
                    matched_detected[di] = True
                    break
        
        # Check URL-encoded phone specifically
        if '%2B1-555' in ex.text:
            print(f"\nURL-encoded phone example: {ex.text!r}")
            print(f"  Expected: {expected_phone}")
            print(f"  Detected: {detected_phone}")
            print(f"  Matched expected: {matched_expected}")
            print(f"  Matched detected: {matched_detected}")
        
        phone_tps += sum(matched_expected)
        phone_fps += len(detected_phone) - sum(matched_detected)
        phone_fns += len(expected_phone) - sum(matched_expected)
    
    print(f"\nPHONE: TP={phone_tps} FP={phone_fps} FN={phone_fns}")

asyncio.run(check())