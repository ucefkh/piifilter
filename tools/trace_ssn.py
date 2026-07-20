"""Exact benchmark scoring per example for SSN."""
import sys, json, re
sys.path.insert(0, '.')
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')

# Import benchmark runner directly via path hack
import importlib.util
spec = importlib.util.spec_from_file_location("br", "tests/benchmark_runner.py")
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

corpus = br.load_golden_corpus()

detector = RegexDetector()
asyncio.run(detector.initialize())

# For each example, run detection and check SSN
all_golden = []
all_detected = []
for i, ex in enumerate(corpus):
    text = ex["text"]
    golden = ex.get("entities", [])
    detected = br.detect_via_detector(text, detector)
    
    # Check if any golden SSN in this example
    ssn_goldens = [e for e in golden if e['type'] == 'SOCIAL_SECURITY']
    ssn_detections = []
    for d in detected:
        n = br._normalize_entity(d)
        if n['type'] == 'SOCIAL_SECURITY':
            ssn_detections.append(n)
    
    if ssn_goldens:
        # Check if at least one SOCIAL_SECURITY detection overlaps
        matched = False
        for g in ssn_goldens:
            for p in ssn_detections:
                if p['start'] < g['end'] and p['end'] > g['start']:
                    matched = True
                    break
        if not matched:
            print(f"Example {i}: SOCIAL_SECURITY golden but NO SOCIAL_SECURITY detected")
            print(f"  Golden: {ssn_goldens}")
            print(f"  All detected: {[(d.entity_type.value, d.text, d.start, d.end) for d in detected]}")
    
    all_golden.extend(golden)
    all_detected.extend([br._normalize_entity(d) for d in detected])

print(f"\nTotal golden: {len(all_golden)}")
print(f"Total detected: {len(all_detected)}")

# Overall scoring
result = score_detections(all_golden, all_detected, threshold=0.0)
print(f"Overall: {result}")

# SSN-only
result_ssn = score_detections(all_golden, all_detected, entity_type='SOCIAL_SECURITY', threshold=0.0)
print(f"SSN (threshold 0.0): {result_ssn}")

result_ssn_bal = score_detections(all_golden, all_detected, entity_type='SOCIAL_SECURITY', threshold=0.50)
print(f"SSN (threshold 0.50): {result_ssn_bal}")