"""Deep debug."""
import sys, json
sys.path.insert(0, '.')
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'tests')
sys.path.insert(0, 'plugins/detector-regex')

import asyncio
from piifilter_detector_regex.detector import RegexDetector

corpus = json.load(open('benchmarks/data/golden_corpus.json'))
examples = corpus['examples']
ex = examples[179]
text = ex['text']
golden = ex['entities']

print(f"Text: {repr(text)}")
print(f"Golden entities: {golden}")

detector = RegexDetector()
asyncio.run(detector.initialize())
import tests.benchmark_runner as br
detected = br.detect_via_detector(text, detector)
print(f"\nDetected entities ({len(detected)}):")
for d in detected:
    print(f"  {d.entity_type.value}: value={repr(d.text)} span={d.start}-{d.end} score={d.raw_score}")

# Score for SOCIAL_SECURITY
result_ssn = br.score_detections(golden, detected, entity_type='SOCIAL_SECURITY', threshold=0.0)
print(f"\nSOCIAL_SECURITY scoring: {result_ssn}")

# Score for MASKED_SSN
result_masked = br.score_detections(golden, detected, entity_type='MASKED_SSN', threshold=0.0)
print(f"MASKED_SSN scoring: {result_masked}")