"""Run full benchmark evaluation for PHONE."""
import sys, asyncio, json
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from recall import load_dataset, make_regex_adapter, evaluate_detector

async def check():
    dataset = load_dataset()
    adapter = make_regex_adapter()
    
    result = await evaluate_detector('regex', dataset, adapter.detect_fn)
    
    # Print PHONE details
    phone_result = result['per_type'].get('PHONE', {})
    print(f"PHONE: TP={phone_result.get('true_positives', 0)} FP={phone_result.get('false_positives', 0)} FN={phone_result.get('false_negatives', 0)}")
    print(f"       recall={phone_result.get('recall', 0):.4f} precision={phone_result.get('precision', 0):.4f}")
    
    # Check confusion matrix
    confusion = result.get('confusion_matrix', {})
    print(f"Confusion for NONE: {json.dumps(confusion.get('NONE', {}), indent=2)}")
    print(f"Confusion for PHONE: {json.dumps(confusion.get('PHONE', {}), indent=2)}")
    
    # Find which examples had PHONE issues
    for ex_result in result.get('example_results', []):
        if 'PHONE' in ex_result.get('expected_types', []) or 'PHONE' in ex_result.get('detected_types', []):
            if ex_result.get('false_positives', 0) > 0 or ex_result.get('false_negatives', 0) > 0:
                print(f"\nExample {ex_result['index']}: {ex_result.get('text_preview', '')[:100]}")
                print(f"  Expected: {ex_result.get('expected_types', [])} Detected: {ex_result.get('detected_types', [])}")
                print(f"  TP={ex_result.get('true_positives')} FP={ex_result.get('false_positives')} FN={ex_result.get('false_negatives')}")

asyncio.run(check())