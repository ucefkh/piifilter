#!/usr/bin/env python3
"""Diagnose CITY detection - run recall benchmark and print per-example results for CITY."""
import sys, asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "benchmarks"))

from recall import load_dataset
from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.models import EntityType


async def main():
    # Load dataset
    dataset_path = PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset.json"
    examples = load_dataset(dataset_path)
    
    # Initialize detector
    detector = RegexDetector()
    
    # Evaluate with arbitration
    from recall import make_pipeline_adapter
    pipeline_detect = make_pipeline_adapter(["regex"])
    
    # Use pipeline adapter to detect
    from recall import evaluate_detector
    results = await evaluate_detector("regex", examples, pipeline_detect)
    
    print(f"\n--- Overall ---")
    print(f"P={results['overall_precision']:.4f} R={results['overall_recall']:.4f} F1={results['overall_f1']:.4f}")
    print(f"TP={results['total_true_positives']} FP={results['total_false_positives']} FN={results['total_false_negatives']}")
    
    if "CITY" in results.get("per_type", {}):
        city = results["per_type"]["CITY"]
        print(f"\nCITY: P={city['precision']:.4f} R={city['recall']:.4f} F1={city['f1']:.4f}")
        print(f"       TP={city['true_positives']} FP={city['false_positives']} FN={city['false_negatives']}")
    
    # Detailed per-example check
    print("\n--- Per-example CITY detection ---")
    for i, ex in enumerate(examples):
        text = ex["text"]
        expected_cities = [e for e in ex.get("entities", []) if e["type"] == "CITY"]
        if not expected_cities:
            continue
        
        # Detect using pipeline adapter
        result = await pipeline_detect(text)
        
        # Filter to CITY candidates
        city_candidates = [c for c in result if c.entity_type == EntityType.CITY]
        
        for exp in expected_cities:
            found = any(c.start == exp["start"] and c.end == exp["end"] for c in city_candidates)
            status = "OK" if found else "FN"
            print(f"  [{i:3d}] {status}: expected '{exp['value']}' [{exp['start']}:{exp['end']}] in '{text}'")
        
        for c in city_candidates:
            expected_match = any(c.start == e["start"] and c.end == e["end"] for e in expected_cities)
            if not expected_match:
                context = text[max(0,c.start-15):c.end+15]
                print(f"  [{i:3d}] FP: got '{c.value}' [{c.start}:{c.end}] score={c.confidence:.3f} ctxt='{context}' in '{text}'")


if __name__ == "__main__":
    asyncio.run(main())