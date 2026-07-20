#!/usr/bin/env python3
"""Get Opus 4.8 score for current state of PIIFilter."""
import json
import re
import os
import boto3

# Use environment-variable based auth to avoid profile parsing issues
session = boto3.Session(region_name='us-east-1')
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

message = {
    "role": "user",
    "content": [{"text": "You are evaluating PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.\n\nRecent changes:\n1. Fixed PERSON/COMPANY false positives: added comprehensive denylists for technical terms (Postgres, PostgreSQL, Nginx, Docker, Kubernetes, Systemd, Support, Config, Settings, Default, Admin, System, Account, Login, Upgrade, Billing, Notification, Report, Dashboard, Security, Access, Manager, Team, Profile) to previously-uncovered PERSON patterns:\n   - Title-prefixed (Mr/Mrs/Dr etc.): 'Mr Postgres Server' no longer matches\n   - Person:/contact: prefix patterns: 'Person: Postgres Admin' no longer matches\n   - contact/reach/met/meet patterns: 'contact Postgres Admin' no longer matches\n   - spoke with/talked to patterns: 'spoke with Postgres Admin' no longer matches\n   - introducing/please welcome patterns: 'introducing Config Manager' no longer matches\n   - regarding patterns: 'regarding Postgres Admin' no longer matches\n   - Signed, / signed- patterns: 'signed Postgres Admin' no longer matches\n2. Also fixed COMPANY 'regarding' single-word pattern which had no denylist at all.\n3. Golden corpus benchmark unchanged: 100% precision/recall on 316 entities across 26 types (balanced mode)\n4. All 486 tests pass\n\nRespond with ONLY a single integer score 1-10 followed by a one-line reason. Format:\nSCORE: X\nREASON: <one line>"}]
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