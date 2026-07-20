"""Debug the phone FPs and FNs in detail."""
import sys, json, asyncio
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from recall import load_dataset
from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.deobfuscator import Deobfuscator

async def check():
    dataset = load_dataset()
    det = RegexDetector()
    
    for ex in dataset:
        # Check for specific texts
        if '123-456-7890 but this is not' in ex.text or 'URL-encoded phone' in ex.text or 'Cyrillic' in ex.text or 'Ҧ' in ex.text:
            print(f"\n{'='*60}")
            print(f"TEXT: {ex.text!r}")
            
            # Show deobfuscator output
            deob = Deobfuscator()
            cleaned, log, text_for_gps = deob(ex.text)
            print(f"DE-OBF: {cleaned!r}")
            
            # Show all detections
            results = await det.detect(ex.text)
            for r in results:
                print(f"  DETECTED: type={r['type']} score={r['score']} value={r['text']!r} span=({r['start']},{r['end']})")
            
            # Show stripped text
            stripped = Deobfuscator._strip_inner_separators(cleaned)
            print(f"STRIPPED: {stripped!r}")

asyncio.run(check())