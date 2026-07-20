"""Check deobfuscation and stripping for example 179."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector, Deobfuscator

text = 'SSN last-4: 6789. Full: XXX-XX-6789'
detector = RegexDetector()
asyncio.run(detector.initialize())

# Directly use the deobfuscator
cleaned, log, text_for_gps = detector._deobfuscator(text)
print(f"Original: {repr(text)}")
print(f"Cleaned:  {repr(cleaned)}")
print(f"GPS tex:  {repr(text_for_gps)}")
print(f"Log: {log}")

# Strip
stripped = Deobfuscator._strip_inner_separators(cleaned)
print(f"Stripped: {repr(stripped)}")

# Run patterns
entities, cc_ssn_spans = detector._run_patterns(stripped)
print(f"\nEntities from _run_patterns ({len(entities)}):")
for e in entities:
    print(f"  {e.entity_type.value}: {repr(e.text)} span={e.start}-{e.end}")
print(f"CC/SSN spans: {cc_ssn_spans}")

# Now run full detect
detected = asyncio.run(detector.detect(text))
print(f"\nFull detect ({len(detected)}):")
for d in detected:
    print(f"  {d.entity_type.value}: text={repr(d.text)} span={d.start}-{d.end}")