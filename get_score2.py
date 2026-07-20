#!/usr/bin/env python3
import boto3, json
session = boto3.Session()
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

prompt = """You are evaluating a PII detection filter benchmark. Score the following results out of 10.

The PIIFilter just completed a recall benchmark with arbitration-on on 150 examples (218 entities).

Overall: Precision=0.9142, Recall=0.9771, F1=0.9446
(Before: P=0.8912, R=0.9771, F1=0.9322)

Key improvements this tick:
- API_KEY: P=1.0000 (was 0.7143) — eliminated 2 false positives
- CITY: P=0.8667 (was 0.6842) — eliminated 4 of 6 false positives

Remaining issues:
- CITY: 1 FN, 2 FP
- DOMAIN: R=0.8889, P=0.8889 (1 FN, 1 FP)
- EMAIL: R=0.9524, P=0.9524 (2 FN, 2 FP)

Rate out of 10. Return ONLY a number from 1-10."""

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'temperature': 1.0},
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}}
)

# Check the response structure
output = response['output']
msg = output['message']
print(f'role: {msg["role"]}')
for item in msg['content']:
    print(f'content key: {list(item.keys())}')
    for k, v in item.items():
        vstr = str(v)[:100]
        print(f'  {k}: {vstr}')
    print()