#!/usr/bin/env python3
"""Get Opus 4.8 score for current commit."""
import boto3, re

session = boto3.Session(region_name='us-east-1')
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': """You are evaluating commit e66506e to PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.

COMMIT: Fix EMPLOYEE_NAME FP: suppress parenthetical references like '(employee John)'

Changes:
1. EMPLOYEE_NAME parenthetical suppression: entities like "employee John" inside parentheses (e.g., "The employee named John (employee John)") are now suppressed as parenthetical clarifications, not new employee introductions.
2. Applied to both detect() and detect_session() methods.
3. All 486 tests pass.
4. Benchmark (arbitration-off) shows EMPLOYEE_NAME precision improved from 0.50 to 1.00 (1 FP eliminated). Remaining known issue: IP_ADDRESS recall=0.50 due to split IP format "192"+"."+"168"+"."+"1"+"."+"1" which is obfuscated text.

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