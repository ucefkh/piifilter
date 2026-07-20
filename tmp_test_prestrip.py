"""Find ALL pre-strip phone detections on the dataset."""
import sys, asyncio, json
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset
from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.patterns import PATTERN_DEFS
import re

async def check():
    dataset = load_dataset()
    
    # Run phone patterns only on pre-strip text for ALL examples where
    # the current filter removes CJK-only phones
    total_presistrip = 0
    non_cjk_presistrip = 0
    
    for ex in dataset:
        deob = Deobfuscator()
        cleaned, log, text_for_gps = deob(ex.text)
        
        # Run phone patterns on pre-strip
        phone_patterns = [(type_name, raw, score) for type_name, raw, score in PATTERN_DEFS if type_name == 'PHONE']
        for type_name, raw_pattern, score in phone_patterns:
            pat = re.compile(raw_pattern)
            for m in pat.finditer(text_for_gps):
                total_presistrip += 1
                val = m.group()
                has_cjk = any(cjk in val for cjk in ("电话", "電話", "電話は", "电话是"))
                if not has_cjk:
                    non_cjk_presistrip += 1
                    # Check if this is a TP (overlaps with expected PHONE entity)
                    is_tp = False
                    for ee in ex.entities:
                        if ee['type'] == 'PHONE':
                            if (m.start() < ee['end'] and m.end() > ee['start']):
                                is_tp = True
                                break
                    if not is_tp:
                        print(f"FP pre-strip phone score={score}: {val!r} at ({m.start()},{m.end()})")
                        print(f"  Text: {ex.text[:120]!r}")
                        print()

    print(f"\nTotal pre-strip phone matches: {total_presistrip}")
    print(f"Non-CJK pre-strip phone matches: {non_cjk_presistrip}")
    
asyncio.run(check())