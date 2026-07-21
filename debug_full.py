"""Debug PERSON FPs — run pipeline and show full detection."""
import sys
import asyncio
import json
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'plugins/detector-presidio/src')

from benchmarks.recall import make_pipeline_adapter, make_arbitration_adapter

async def main():
    texts = [
        "Uma Carter (uma.carter@temp-services.co.uk) works at Aviato",
        "Zack Jackson (zack.jackson@mail.company.io) works at Tyrell Corp",
        "Sofia King (sofia.king@bigpharma.com) works at Oceanic Airlines",
        "Aaron Lee (aaron.lee@temp-services.co.uk) works at Dunder Mifflin",
    ]
    
    # Raw pipeline
    pipeline = await make_pipeline_adapter()
    
    # Arbitration pipeline
    arb = make_arbitration_adapter(pipeline)
    
    for text in texts:
        print(f"\n=== TEXT: {text} ===")
        
        # Raw pipeline output
        raw = await pipeline.detect_fn(text)
        print("PIPELINE RAW:")
        for r in raw:
            det = r.get('detector', '?')
            et = r.get('entity_type', '?')
            st = r.get('start', 0)
            en = r.get('end', 0)
            val = text[st:en]
            print(f"  [{det}] {et} at [{st}:{en}] = '{val}' (score={r.get('score',r.get('confidence','?'))})")
        
        # Arbitrated output
        arb_results = await arb.detect_fn(text)
        print("ARBITRATED:")
        for r in arb_results:
            et = r.get('entity_type', '?')
            st = r.get('start', 0)
            en = r.get('end', 0)
            val = text[st:en]
            print(f"  {et} at [{st}:{en}] = '{val}' (conf={r.get('confidence',r.get('score','?'))})")

asyncio.run(main())