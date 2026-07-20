"""Find all SOCIAL_SECURITY golden entries and check detection for each."""
import sys, json
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'tests')
import asyncio, subprocess
from piifilter_detector_regex.detector import RegexDetector
import tests.benchmark_runner as br

corpus = json.load(open('benchmarks/data/golden_corpus.json'))
examples = corpus['examples']

# Find all examples with SOCIAL_SECURITY golden
ssn_examples = []
for i, ex in enumerate(examples):
    for e in ex.get('entities', []):
        if e['type'] == 'SOCIAL_SECURITY':
            ssn_examples.append((i, ex, e))

print(f"Total SOCIAL_SECURITY golden: {len(ssn_examples)}")
for idx, ex, e in ssn_examples:
    start, end = e['start'], e['end']
    text_snippet = ex['text'][start:end]
    print(f"  Example {idx}: span={start}-{end} value={repr(text_snippet)} context={repr(ex['text'][max(0,start-10):end+10])}")

# Now run detection on each and see what we get
detector = RegexDetector()
asyncio.run(detector.initialize())

print("\nDetection results for SSN examples:")
golden_missed = []
for idx, ex, golden_ent in ssn_examples:
    text = ex['text']
    detected = br.detect_via_detector(text, detector)
    # Find what type covers the golden span
    gs, ge = golden_ent['start'], golden_ent['end']
    found = False
    for d in detected:
        if d.start <= gs and ge <= d.end:
            print(f"  Example {idx}: golden SOCIAL_SECURITY at {gs}-{ge} -> detected as {d.entity_type.value} at {d.start}-{d.end} value={repr(d.text)} score={d.raw_score}")
            found = True
            break
    if not found:
        print(f"  Example {idx}: golden SOCIAL_SECURITY at {gs}-{ge} NOT FOUND in detection!")
        golden_missed.append((idx, golden_ent))

print(f"\nMissed: {len(golden_missed)}")
for idx, e in golden_missed:
    print(f"  Example {idx}: {e}")