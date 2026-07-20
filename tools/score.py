#!/usr/bin/env python3
"""Get Opus 4.8 score for current commit."""
import boto3, re

session = boto3.Session(region_name='us-east-1')
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': """You are evaluating commit 0d7c256 to PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.

COMMIT: Fix EMPLOYEE_NAME FP: suppress parenthetical duplicates only (non-paren ref must exist)

Changes:
1. EMPLOYEE_NAME parenthetical suppression: parenthetical references like "(employee John)" are suppressed ONLY when they duplicate an already-detected non-parenthetical EMPLOYEE_NAME reference. Standalone parenthetical employee introductions are preserved.
2. Applied to both detect() and detect_session().
3. All 486 tests pass.
4. All entity types meet recall >= 0.95 and real precision >= 0.85. EMPLOYEE_NAME real precision 1.00 (was 0.50).

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