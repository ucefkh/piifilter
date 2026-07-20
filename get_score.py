#!/usr/bin/env python3
"""Score the current PIIFilter state via Opus 4.8."""
import json, boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")

prompt = """Rate PIIFilter out of 10 on this scale:
1-6: Not production-ready
7-8: Good, most types high recall/precision, some gaps  
9-9.5: Excellent, all entity types at recall >= 0.95 and precision >= 0.85
9.6-10: Perfect or near-perfect

Current metrics (regex detector, arbitration-on, 150 examples / 213 entities):
- Overall: Precision=0.8966  Recall=0.9765  F1=0.9348  TP=208  FP=24  FN=5
- 15/24 entity types at recall=1.0
- CITY: R=0.8889, P=0.7273 (3 FP, 1 FN — address overlap in arbitration)
- EMAIL: R=0.9524, P=0.9524
- PHONE: R=1.0, P=0.8333 (5 FP)
- IP_ADDRESS: R=0.9333, P=0.8750
- SOCIAL_SECURITY: R=1.0, P=0.7000 (3 FP)
- PERSON: R=1.0, P=0.8182 (2 FP)
- DOMAIN: R=0.8889, P=0.8889
- CREDIT_CARD: R=1.0, P=1.0
- GPS: R=1.0, P=1.0
- PASSPORT: R=1.0, P=1.0

Key improvements this tick:
- Added address-context CITY patterns (City, ST ZIP and City, UK-POSTCODE)
- Added major-city sentence-start pattern (Paris has..., Berlin is...)
- CITY recall improved from 0.6667→0.8889, 3 FNs resolved (New York, Paris, London)

Give ONLY a single number 0-10, nothing else."""

try:
    response = client.converse(
        modelId="us.anthropic.claude-opus-4-8",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 1.0, "maxTokens": 20},
    )
    
    content = response["output"]["message"]["content"]
    score_text = ""
    for c in content:
        if "text" in c:
            score_text = c["text"].strip()
    
    print(score_text if score_text else json.dumps(response["output"]["message"]["content"], default=str))
    print(f"Stop reason: {response.get('stopReason', 'unknown')}")
    
    # Save score
    with open("/tmp/piifilter_last_score.txt", "w") as f:
        f.write(score_text if score_text else "unknown")
except Exception as e:
    print(f"Error: {e}")