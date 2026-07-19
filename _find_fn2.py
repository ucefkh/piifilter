"""Find SSN FNs using the exact same benchmark logic."""
import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/core/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src')

from benchmarks.recall import load_dataset, stratified_train_test_split, make_regex_adapter

data_path = '/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/pii_dataset_v2.json'

examples = load_dataset(Path(data_path))
train, test = stratified_train_test_split(examples, test_size=0.2, random_state=42)

print(f"Test examples: {len(test)}")

ssn_test = [t for t in test if any(e["type"] == "SOCIAL_SECURITY" for e in t.entities)]
print(f"SSN test examples: {len(ssn_test)}")

adapter = make_regex_adapter()

async def evaluate():
    fn_details = []
    tp_count = 0
    fn_count = 0
    
    for te in test:
        ssn_gt = [e for e in te.entities if e["type"] == "SOCIAL_SECURITY"]
        if not ssn_gt:
            continue
        
        results = await adapter.detect_fn(te.text)
        ssn_detected = [r for r in results if r["entity_type"] == "SOCIAL_SECURITY"]
        
        for gt in ssn_gt:
            found = any(
                d["start"] <= gt["start"] and d["end"] >= gt["end"]
                for d in ssn_detected
            )
            if found:
                tp_count += 1
            else:
                fn_count += 1
                fn_details.append((te, gt, ssn_detected))
    
    print(f"\nSSN TP: {tp_count}, FN: {fn_count}")
    print(f"SSN Recall: {tp_count / (tp_count + fn_count):.4f}")
    
    print(f"\n=== FALSE NEGATIVES ===")
    for i, (te, gt, detected) in enumerate(fn_details):
        print(f"\nFN {i}:")
        print(f"  Text:    {repr(te.text[:130])}")
        print(f"  GT val:  {repr(gt['value'])}, GT span: [{gt['start']}:{gt['end']}]")
        if detected:
            for d in detected:
                print(f"  Detected: {repr(d['value'])} [{d['start']}:{d['end']}] score={d['score']}")

asyncio.run(evaluate())