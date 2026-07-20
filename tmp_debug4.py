"""Detailed debug of URL-encoded phone detection."""
import sys, asyncio
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.deobfuscator import Deobfuscator

async def check():
    det = RegexDetector()
    
    text = 'URL-encoded phone: %2B1-555-123-4567'
    print(f"Text: {text!r}")
    print(f"Labeled entity: '%2B1-555-123-4567' at spans (19, 36)")
    
    # Deobfuscate
    deob = Deobfuscator()
    cleaned, log, text_for_gps = deob(text)
    print(f"Cleaned:     {cleaned!r}")
    print(f"GPS text:    {text_for_gps!r}")
    
    stripped = Deobfuscator._strip_inner_separators(cleaned)
    print(f"Stripped:    {stripped!r}")
    
    # Detect
    results = await det.detect(text)
    print(f"\nDetected {len(results)} entities:")
    for r in results:
        print(f"  type={r['type']} score={r['score']} value={r['text']!r} span=({r['start']},{r['end']})")
        print(f"    in context: {text[r['start']:r['end']]!r}")

asyncio.run(check())