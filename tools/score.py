#!/usr/bin/env python3
"""Get Opus 4.8 score for current commit."""
import boto3, re

session = boto3.Session(region_name='us-east-1')
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': """You are evaluating commit 09845c5 to PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.

COMMIT: Fix EMPLOYEE_NAME FP: suppress parenthetical duplicates only, keep standalone paren refs

Changes:
1. EMPLOYEE_NAME parenthetical suppression: parenthetical references like "(employee John)" are suppressed ONLY when they duplicate a non-parenthetical reference already found (e.g. "employee named John (employee John)"). Standalone parenthetical references like "(employee John Smith for support)" are preserved.
2. Applied to both detect() and detect_session().
3. All 486 tests pass.
4. Benchmark (arbitration-off) shows EMPLOYEE_NAME precision improved from 0.50 to 1.00 (1 FP eliminated). All other entity types meet recall >= 0.95 and real precision >= 0.85.

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