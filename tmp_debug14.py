"""Check 3-3-4 pre-strip phone FPs."""
import sys, asyncio
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS
import re

async def check():
    dataset = load_dataset()
    
    prestrip_tp = 0
    prestrip_fp = 0
    prestrip_seen = set()
    
    for ex in dataset:
        deob = Deobfuscator()
        cleaned, log, text_for_gps = deob(ex.text)
        
        phone_patterns = [(tn, rp, sc) for tn, rp, sc in PATTERN_DEFS if tn == 'PHONE']
        for tn, rp, sc in phone_patterns:
            pat = re.compile(rp)
            for m in pat.finditer(text_for_gps):
                val = m.group()
                has_cjk = any(cjk in val for cjk in ("电话", "電話", "電話は", "电话是"))
                has_plus = '+' in val
                
                # Only care about scores >= 0.70
                if sc < 0.70:
                    continue
                if has_cjk or has_plus:
                    continue
                
                key = (ex.text, m.start(), m.end(), val)
                if key in prestrip_seen:
                    continue
                prestrip_seen.add(key)
                
                is_tp = False
                for ee in ex.entities:
                    if ee['type'] == 'PHONE' and (m.start() < ee['end'] and m.end() > ee['start']):
                        is_tp = True
                        break
                
                if is_tp:
                    prestrip_tp += 1
                    print("TP pre-strip phone score=%s: %r at (%d,%d)" % (sc, val.strip(), m.start(), m.end()))
                    print("  Text: %r" % ex.text[:120])
                else:
                    prestrip_fp += 1
                    print("FP pre-strip phone score=%s: %r at (%d,%d)" % (sc, val.strip(), m.start(), m.end()))
                    print("  Text: %r" % ex.text[:120])
    
    print("\nNon-CJK/non-plus pre-strip phones with score >= 0.70: TP=%d FP=%d" % (prestrip_tp, prestrip_fp))

asyncio.run(check())