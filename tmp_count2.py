import json

with open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/recall-results.json') as f:
    data = json.load(f)

tp = data.get('summary', {}).get('total_tp', 0)
fn = data.get('summary', {}).get('total_fn', 0)
fp = data.get('summary', {}).get('total_fp', 0)
print(f"Full set: TP={tp} FN={fn} FP={fp} Total_entities={tp+fn}")

with open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/recall-results-heldout.json') as f:
    data2 = json.load(f)

tp2 = data2.get('summary', {}).get('total_tp', 0)
fn2 = data2.get('summary', {}).get('total_fn', 0)
fp2 = data2.get('summary', {}).get('total_fp', 0)
print(f"Heldout: TP={tp2} FN={fn2} FP={fp2} Total_entities={tp2+fn2}")
print(f"Total detections across both = {tp + fn + tp2 + fn2}")