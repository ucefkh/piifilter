"""Check threshold for MASKED_SSN."""
import sys, json
sys.path.insert(0, 'tests')
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location("br", "tests/benchmark_runner.py")
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

# Check threshold
threshold = br.get_threshold("balanced", "MASKED_SSN", None)
print(f"MASKED_SSN threshold in balanced mode: {threshold}")

threshold_ssn = br.get_threshold("balanced", "SOCIAL_SECURITY", None)
print(f"SOCIAL_SECURITY threshold in balanced mode: {threshold_ssn}")

# Also check the score of the detection
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

text = 'SSN last-4: 6789. Full: XXX-XX-6789'
detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))
for d in detected:
    n = br._normalize_entity(d)
    print(f"Detection: type={n['type']}, score={n['score']}")
    print(f"  Passes threshold {threshold}? {n['score'] >= threshold}")