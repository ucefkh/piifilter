"""Find which SOCIAL_SECURITY golden entities match which detections."""
import json
import subprocess
# Re-run benchmark and pipe output
result = subprocess.run(
    ['python3', 'tests/benchmark_runner.py', '--mode', 'balanced', '--json'],
    capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai'
)
bench = json.loads(result.stdout)

# Now iterate examples and check per-example
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

corpus = json.load(open('benchmarks/data/golden_corpus.json'))
examples = corpus['examples']

detector = RegexDetector()
asyncio.run(detector.initialize())

# For each SSN golden example, print what detections cover that span
for i, ex in enumerate(examples):
    golden_ssns = [e for e in ex.get('entities', []) if e['type'] == 'SOCIAL_SECURITY']
    if not golden_ssns:
        continue
    
    detected = asyncio.run(detector.detect(ex['text']))
    
    for g in golden_ssns:
        gs, ge = g['start'], g['end']
        gv = g['value']
        # Find any detected entity overlapping this span
        overlapping = [d for d in detected if d.start < ge and d.end > gs]
        if overlapping:
            for d in overlapping:
                print(f"Ex {i}: golden SSN [{gs}:{ge}]={repr(gv)} -> detected {d.entity_type.value} [{d.start}:{d.end}]={repr(d.text)} score={d.raw_score}")
        else:
            print(f"Ex {i}: golden SSN [{gs}:{ge}]={repr(gv)} -> NOT FOUND")