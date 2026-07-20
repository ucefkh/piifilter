"""Check what pre-strip phones with + prefix and score >= 0.80 would add as FPs."""
import sys, asyncio, re
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS

async def check():
    dataset = load_dataset()
    
    plus_phones_fp = 0
    plus_phones_tp = 0
    cjk_phones = 0
    
    for ex in dataset:
        deob = Deobfuscator()
        cleaned, log, text_for_gps = deob(ex.text)
        
        # Run phone patterns on pre-strip
        phone_patterns = [(type_name, raw, score) for type_name, raw, score in PATTERN_DEFS if type_name == 'PHONE']
        for type_name, raw_pattern, score in phone_patterns:
            pat = re.compile(raw_pattern)
            for m in pat.finditer(text_for_gps):
                val = m.group()
                has_cjk = any(cjk in val for cjk in ("电话", "電話", "電話は", "电话是"))
                
                if has_cjk:
                    cjk_phones += 1
                    continue
                
                # Check if this has + prefix and score >= 0.80
                has_plus = '+' in val
                if has_plus and score >= 0.80:
                    # Is this a TP?
                    is_tp = False
                    for ee in ex.entities:
                        if ee['type'] == 'PHONE':
                            if (m.start() < ee['end'] and m.end() > ee['start']):
                                is_tp = True
                                break
                    if is_tp:
                        plus_phones_tp += 1
                        print(f"TP +-prestrip phone score={score}: {val!r} at ({m.start()},{m.end()})")
                        print(f"  Text: {ex.text[:120]!r}")
                    else:
                        plus_phones_fp += 1
                        print(f"FP +-prestrip phone score={score}: {val!r} at ({m.start()},{m.end()})")
                        print(f"  Text: {ex.text[:120]!r}")

    print(f"\nCJK phones: {cjk_phones}")
    print(f"Plus-prefix TP phones: {plus_phones_tp}")
    print(f"Plus-prefix FP phones: {plus_phones_fp}")

asyncio.run(check())