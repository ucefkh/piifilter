"""Check keyword-prefixed pre-strip phone FPs."""
import sys
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from recall import load_dataset
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS
import re, asyncio

async def check():
    dataset = load_dataset()
    
    keyword_tp = 0
    keyword_fp = 0
    
    for ex in dataset:
        deob = Deobfuscator()
        cleaned, log, text_for_gps = deob(ex.text)
        
        # Run phone patterns on pre-strip
        phone_patterns = [(tn, rp, sc) for tn, rp, sc in PATTERN_DEFS if tn == 'PHONE']
        for tn, rp, sc in phone_patterns:
            pat = re.compile(rp)
            for m in pat.finditer(text_for_gps):
                val = m.group()
                has_cjk = any(cjk in val for cjk in ("电话", "電話", "電話は", "电话是"))
                has_plus = '+' in val
                
                # Check for keyword context
                has_keyword = any(kw in val.lower() for kw in ['phone', 'tel', 'mobile', 'cell', 'call'])
                
                if has_keyword and sc >= 0.80 and not has_cjk and not has_plus:
                    is_tp = False
                    for ee in ex.entities:
                        if ee['type'] == 'PHONE' and (m.start() < ee['end'] and m.end() > ee['start']):
                            is_tp = True
                            break
                    if is_tp:
                        keyword_tp += 1
                        print("TP keyword pre-strip phone score=%s: %r at (%d,%d)" % (sc, val, m.start(), m.end()))
                        print("  Text: %r" % ex.text[:120])
                    else:
                        keyword_fp += 1
                        print("FP keyword pre-strip phone score=%s: %r at (%d,%d)" % (sc, val, m.start(), m.end()))
                        print("  Text: %r" % ex.text[:120])
    
    print("\nKeyword-prefixed TP: %d" % keyword_tp)
    print("Keyword-prefixed FP: %d" % keyword_fp)

asyncio.run(check())