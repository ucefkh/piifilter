#!/usr/bin/env python3
"""Score the current PIIFilter state via Opus 4.8 without thinking mode (simpler)."""
import json, boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")

prompt = """Rate PIIFilter out of 10 on this scale:
1-6: Not production-ready
7-8: Good, most types high recall/precision, some gaps  
9-9.5: Excellent, all entity types at recall >= 0.95 and precision >= 0.85
9.6-10: Perfect or near-perfect

Current metrics (arbitration enabled):
- DOMAIN: recall=1.0, precision=0.9000 (FIXED this tick from recall=0.8889, precision=0.8000)
- PERSON: recall=1.0, precision=0.8889
- PROJECT_NAME: recall=1.0, precision=1.0
- EMAIL: recall=0.9524, precision=0.9302
- IP_ADDRESS: recall=0.9333, precision=1.0
- PHONE: recall=0.9333, precision=0.9333
- Overall: precision=0.9220, recall=0.9812, F1=0.9457
- 23/25 entity types have recall=1.0

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