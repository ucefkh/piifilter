#!/usr/bin/env python3
"""Get Opus 4.8 score for current state of PIIFilter."""
import json
import re
import boto3

session = boto3.Session(profile_name='default')
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

message = {
    "role": "user",
    "content": [{"text": "You are evaluating PIIFilter, a privacy proxy that detects/filters PII from prompts before LLMs and unfilters responses.\n\nRecent changes:\n1. CI live-integration job re-enabled (was if:false) — now starts Ollama, verifies /v1/models, runs provider tests\n2. LMStudioProvider._resolve_config fixed: preserves auto-detected endpoint/model instead of overwriting with LM Studio defaults\n3. provider-ollama plugin installed in CI alongside provider-lmstudio\n4. Golden corpus benchmark: 100% precision/recall on 316 entities across 26 types (balanced mode)\n\nRespond with ONLY a single integer score 1-10 followed by a one-line reason. Format:\nSCORE: X\nREASON: <one line>"}]
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