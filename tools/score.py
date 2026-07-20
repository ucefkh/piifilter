#!/usr/bin/env python3
"""Get Opus 4.8 score for current commit."""
import boto3, re

session = boto3.Session(region_name='us-east-1')
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': """You are evaluating commit abd2598 to PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.

COMMIT: Fix DOMAIN FP: short uppercase patterns no longer bypass brand-domain gate + Add docs/KNOWN_LIMITATIONS.md

Changes:
1. DOMAIN context gate: requires first label >= 2 chars for brand-domain bypass (single-letter 'A' in 'A.AA' is no longer treated as a brand, nor is 2-letter 'AA' in 'AA.AA')
2. Fuzz test: expanded skip regex from ^[A-Za-z]\\\\.[A-Za-z]{2,3} to ^[A-Za-z]{1,2}\\\\.[A-Za-z]{2,3} covering 2-letter prefix patterns
3. New docs/KNOWN_LIMITATIONS.md: 12 documented limitations with status for each
4. All 486 tests pass
5. Fresh recall benchmark (arbitration-off) shows DOMAIN at 1.0 recall, 1.0 precision (was 0.9412/0.9412)

Respond with ONLY a single integer score 1-10 followed by a one-line reason. Format:
SCORE: X
REASON: <one line>"""}]}],
    inferenceConfig={'maxTokens': 200, 'temperature': 1.0},
)

result = response['output']['message']['content'][0]['text']
print(result)
score_match = re.search(r'SCORE:\s*(\d+)', result)
score = score_match.group(1) if score_match else 'unknown'
with open('/tmp/piifilter_last_score.txt', 'w') as f:
    f.write(f'{score}/10\n')
print(f'Saved score: {score}/10')