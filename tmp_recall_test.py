#!/usr/bin/env python3
"""Run recall benchmark focused on regex detector to see CC/SSN recall."""
import sys, json, re
from pathlib import Path

PROJECT_ROOT = Path("/home/ucefkh/projects/privacy-proxy-ai")
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType
from piifilter.shared.deobfuscator import Deobfuscator

import asyncio

async def main():
    detector = RegexDetector()
    await detector.initialize()
    
    # Load pii_dataset_v2.json (biggest dataset)
    with open(PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset_v2.json") as f:
        data = json.load(f)
    examples = data.get("examples", [])
    
    # Focus on CREDIT_CARD and SOCIAL_SECURITY
    results = {"CREDIT_CARD": {"tp": 0, "fn": 0}, "SOCIAL_SECURITY": {"tp": 0, "fn": 0}}
    cc_misses = []
    ssn_misses = []
    
    for ex in examples:
        if isinstance(ex, str):
            continue
        text = ex["text"]
        entities = ex.get("entities", [])
        
        # Detect
        detected = await detector.detect(text)
        detected_by_type = {}
        for d in detected:
            detected_by_type.setdefault(d.entity_type.value, []).append(d)
        
        for e in entities:
            etype = e["type"]
            if etype not in ("CREDIT_CARD", "SOCIAL_SECURITY"):
                continue
            estart, eend = e["start"], e["end"]
            evalue = text[estart:eend]
            edigits = re.sub(r'[^0-9]', '', evalue)
            
            # Check if detected
            found = False
            for d in detected_by_type.get(etype, []):
                dvalue = d.value
                ddigits = re.sub(r'[^0-9]', '', dvalue)
                if ddigits and edigits and (ddigits == edigits or ddigits in edigits or edigits in ddigits):
                    found = True
                    break
            
            if found:
                results[etype]["tp"] += 1
            else:
                results[etype]["fn"] += 1
                ctx = text[max(0,estart-30):estart] + "|" + text[eend:eend+30]
                miss_info = {"span": evalue, "digits": edigits, "ctx": ctx}
                if etype == "CREDIT_CARD":
                    cc_misses.append(miss_info)
                else:
                    ssn_misses.append(miss_info)
    
    print("=== Recall Results (pii_dataset_v2.json) ===")
    for etype in ["CREDIT_CARD", "SOCIAL_SECURITY"]:
        r = results[etype]
        total = r["tp"] + r["fn"]
        recall = r["tp"] / total if total > 0 else 0
        print(f"  {etype}: TP={r['tp']}, FN={r['fn']}, Total={total}, Recall={recall:.4f}")
    
    print("\n=== CC Misses ===")
    for m in cc_misses[:20]:
        print(f"  span={m['span']!r:45s} digits={m['digits']:20s} ctx={m['ctx']}")
    
    print("\n=== SSN Misses ===")
    for m in ssn_misses[:30]:
        print(f"  span={m['span']!r:45s} digits={m['digits']:20s} ctx={m['ctx']}")

asyncio.run(main())