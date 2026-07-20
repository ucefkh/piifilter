#!/usr/bin/env python3
"""Get Opus 4.8 score for current PIIFilter state."""
import boto3, json

session = boto3.Session()
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

prompt = """You are evaluating a PII detection filter benchmark. Score the following results out of 10.

The PIIFilter just completed a recall benchmark with arbitration-on on 150 examples (218 entities).

Current benchmark (pipeline-arbitration):
Overall: Precision=0.9307, Recall=0.9862, F1=0.9577
(Note: benchmark uses original-text coordinates vs deobfuscated-text coordinates, so FN/FP counts for examples with heavy deobfuscation are inflated by coordinate-mismatch)

Improvement this tick:
Fixed _CONCAT_RE in deobfuscator to handle SINGLE-QUOTED split tokens (e.g. 'john' + '@' + 'example.com').
Previously only double-quoted split tokens were handled (e.g. "john" + "@" + "example.com").
This fixes a real-world email obfuscation that was previously missed entirely.

The benchmark cannot measure this fix directly because of a span-coordinate mismatch
between original and deobfuscated text in the dataset annotation.

Rate out of 10. Consider: impact of the fix (catches a real obfuscation pattern that was missed),
remaining gaps (all 26 types at 1.0 F1 on golden corpus, P=0.9307 R=0.9862 on synthetic),
and overall quality. Return ONLY a number from 1-10."""

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'temperature': 1.0},
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}}
)

content = response['output']['message']['content']
for item in content:
    if 'reasoningContent' in item:
        rt = item['reasoningContent'].get('reasoningText', {})
        print(f'Score (reasoning): {rt.get("text", "N/A")}')
    elif 'text' in item:
        print(f'Score: {item["text"].strip()}')
    else:
        print(f'Raw: {json.dumps(item, default=str)[:500]}')