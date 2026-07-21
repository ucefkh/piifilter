"""Check possessive PERSON FPs more carefully"""
import json, sys
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-presidio/src')
sys.path.insert(0, '/home/ucefkh/projects/privacy-proxy-ai/core/src')

from benchmarks.recall import make_pipeline_adapter, make_arbitration_adapter
import asyncio

async def check(text, label):
    pipe = await make_pipeline_adapter()
    arb = make_arbitration_adapter(pipe)
    raw = await pipe.detect_fn(text)
    arb_r = await arb.detect_fn(text)
    
    print(f'\n=== {label}: {text} ===')
    print(f'Raw pipeline ({len(raw)} detections):')
    for d in raw:
        print(f'  {d["entity_type"]}="{d["value"]}" det={d["detector"]} score={d.get("score","")}')
    print(f'Arbitration ({len(arb_r)} detections):')
    for d in arb_r:
        print(f'  {d["entity_type"]}="{d["value"]}" det={d["detector"]} score={d.get("score","")}')

async def main():
    await check("Yuki's SSN is 034-60-5580 — keep it confidential.", 'FP-Possessive-1')
    await check("Mei's SSN is 210-78-8977 — keep it confidential.", 'FP-Possessive-2')
    await check("Thabo's SSN is 831-49-2815 — keep it confidential.", 'FP-Possessive-3')

asyncio.run(main())