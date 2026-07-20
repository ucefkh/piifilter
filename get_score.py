#!/usr/bin/env python3
"""Get Opus 4.8 score."""
import boto3, json

session = boto3.Session()
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

prompt = """You are evaluating a PII detection filter benchmark. Score the following results out of 10.

The PIIFilter just completed a recall benchmark with arbitration-on on 150 examples (218 entities).

Overall: Precision=0.9307, Recall=0.9862, F1=0.9577

Key improvements this tick:
1. Fixed split-token deobfuscation ordering
2. Added PHONE demo/teaching context suppression (phone-like, not a real phone, example phone, fake number)

Rate out of 10. Consider: impact of improvements, remaining gaps, and overall quality. Return ONLY a number from 1-10."""

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'temperature': 1.0},
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}}
)

# Extract text from response - handle thinking format
content = response['output']['message']['content']
for item in content:
    if 'reasoningContent' in item:
        # Thinking mode - look for text within reasoning
        rt = item['reasoningContent'].get('reasoningText', {})
        print(f'Score (reasoning): {rt.get("text", "N/A")}')
    elif 'text' in item:
        print(f'Score: {item["text"].strip()}')
    else:
        print(f'Raw: {json.dumps(item, default=str)[:500]}')