#!/usr/bin/env python3
"""Score the current PIIFilter state via Opus 4.8 - no thinking mode."""
import json, boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")

prompt = """Rate PIIFilter out of 10 on this scale:
1-6: Not production-ready
7-8: Good, most types high recall/precision, some gaps
9-9.5: Excellent, all entity types at recall >= 0.95 and precision >= 0.85
9.6-10: Perfect or near-perfect

Current metrics:
- PROJECT_NAME: recall=1.0, precision=1.0 (just fixed from 0.5714)
- EMAIL: recall=0.9459, precision=0.8750
- IP_ADDRESS: recall=0.9231, precision=0.8000
- PERSON: recall=0.8571, precision=0.5455
- 21/25 types have recall=1.0

Give ONLY a single number 0-10, nothing else."""

response = client.converse(
    modelId="us.anthropic.claude-opus-4-8",
    messages=[{"role": "user", "content": [{"text": prompt}]}],
    inferenceConfig={"temperature": 1.0, "maxTokens": 10},
)

content = response["output"]["message"]["content"]
for c in content:
    for key in c:
        val = c[key]
        if isinstance(val, str):
            print(f"{key}: {val.strip()}")