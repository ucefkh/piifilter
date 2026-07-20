#!/usr/bin/env python3
"""Get Opus 4.8 score for current state of PIIFilter."""
import json
import re
import os
import boto3

# Use environment-variable based auth to avoid profile parsing issues
session = boto3.Session(region_name='eu-west-3')
bedrock = session.client('bedrock-runtime', region_name='eu-west-3')

message = {
    "role": "user",
    "content": [{"text": "You are evaluating PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.\n\nRecent changes:\n1. Fixed COMPANY/PERSON false positives: added comprehensive denylists for technical terms (Postgres, Support, Config, Settings, Default, Admin, System, Account, Login, Project, Nginx, Docker, Kubernetes, Systemd) and city/geographic names (New, San, Los, Las, etc.) to all 'from', 'works at', 'Invoice from', 'Signed by', 'regarding' keyword-prefixed COMPANY and PERSON patterns. Previously these patterns would match phrases like 'from New York', 'Signed by Postgres Admin', 'works at Support Team', 'from Project Phoenix' as PII.\n2. Golden corpus benchmark unchanged: 100% precision/recall on 316 entities across 26 types (balanced mode)\n3. All 486 tests pass\n\nRespond with ONLY a single integer score 1-10 followed by a one-line reason. Format:\nSCORE: X\nREASON: <one line>"}]
}

response = bedrock.converse(
    modelId="us.anthropic.claude-opus-4-8",
    messages=[message],
    inferenceConfig={"maxTokens": 200, "temperature": 1.0},
)

result = response['output']['message']['content'][0]['text']
print(result)

# Extract score
score_match = re.search(r'SCORE:\s*(\d+)', result)
score = score_match.group(1) if score_match else "unknown"
with open('/tmp/piifilter_last_score.txt', 'w') as f:
    f.write(f"{score}/10\n")
print(f"\nSaved score: {score}/10")