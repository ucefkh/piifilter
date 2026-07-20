#!/usr/bin/env python3
"""Score the current PIIFilter state via Opus 4.8 without thinking mode (simpler)."""
import json, boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")

prompt = """Rate PIIFilter out of 10 on this scale:
1-6: Not production-ready
7-8: Good, most types high recall/precision, some gaps  
9-9.5: Excellent, all entity types at recall >= 0.95 and precision >= 0.85
9.6-10: Perfect or near-perfect

Current metrics (pipeline-arbitration, held-out 20%, 473 test examples / 540 entities):
- Overall: Precision=0.8929  Recall=0.9111  F1=0.9019
- CC real recall: 0.9667 (29/30 real, masked excluded), precision: 0.9667
- SSN real recall: 0.8947 (36 TP / 19 real, masked excluded), precision: 0.9730
- DOMAIN: recall=1.0, precision=0.4688 (high FP from word-boundary regex)
- CITY: recall=0.5556, precision=0.2632 (short names clash with common words)
- GPS: recall=1.0, precision=1.0 (pipeline-arb)
- BANK_ACCOUNT: recall=1.0, precision=0.8750
- COUNTRY: recall=0.6667, precision=0.5455
- EMAIL: recall=0.9818, precision=1.0
- IP_ADDRESS: recall=0.9783, precision=1.0
- PHONE: recall=0.9825, precision=1.0
- PERSON: recall=1.0, precision=0.6842 (FP from name-like terms)
- 12/26 entity types at recall=1.0, 9/26 at precision>=0.94
- ADDRESS: recall=0.8889, precision=0.9412
- URL: recall=0.6562, precision=0.9130

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
    import traceback
    traceback.print_exc()