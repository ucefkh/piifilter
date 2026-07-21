"""Debug Subdomain FP and Contact X at FPs"""
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
    print(f'Raw pipeline:')
    for d in raw:
        print(f'  {d["entity_type"]}="{d["value"]}" det={d["detector"]} score={d.get("score","")}')
    print(f'Arbitration:')
    for d in arb_r:
        print(f'  {d["entity_type"]}="{d["value"]}" det={d["detector"]} score={d.get("score","")}')

async def main():
    await check('Subdomain: api.hubbase.app', 'FP-Subdomain-1')
    await check('Subdomain: api.tryvault.tech', 'FP-Subdomain-2')
    await check('Contact Fatima at +1-661-699-8185', 'FP-Contact')
    await check('Contact Hiroshi at +1-424-986-5517', 'FP-Contact-2')
    await check("Yuki's SSN is 034-60-5580", 'FP-Possessive')
    await check("Thabo's SSN is 831-49-2815", 'FP-Possessive-2')

asyncio.run(main())