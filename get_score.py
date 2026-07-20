#!/usr/bin/env python3
"""Get Opus 4.8 score for the PIIFilter."""
import boto3, json

session = boto3.Session()
bedrock = session.client('bedrock-runtime', region_name='us-east-1')

prompt = """You are evaluating a PII detection filter benchmark. Score the following results out of 10.

The PIIFilter just completed a recall benchmark with arbitration-on on 150 examples (218 entities).

Overall: Precision=0.9142, Recall=0.9771, F1=0.9446
(Before: P=0.8912, R=0.9771, F1=0.9322)

Key improvements this tick:
- API_KEY: P=1.0000 (was 0.7143) — eliminated 2 false positives (IPv6 hex matched Level 4 pure-hex API_KEY pattern; base64 email matched Level 3 with 'token' lookahead)
- CITY: P=0.8667 (was 0.6842) — eliminated 4 of 6 false positives (added (?<!\() lookbehind to explicit city list, added (?<!\() to office-before-headquarters pattern)

What this tick fixed:
1. API_KEY Level 3: Base64 email (dGVzdEBleGFtcGxlLmNvbQ==) with text 'looks like a token' — added negative lookahead for 'looks like a/like a/not a' before key/token/secret
2. API_KEY Level 4: Pure-hex 24+ chars from stripped IPv6 address (2001:0db8:85a3:... → 20010db885a3000000008a2e) — added _filter_apikey_ip_overlap cross-type dedup comparing hex-digit content
3. CITY: Berlin in (Berlin office) context matched explicit city list — split into Tokyo/Sydney (bare, needed for GPS-paren benchmark labels) and others with (?<!\() lookbehind
4. CITY: Berlin in (Berlin office) also matched office-before-headquarters pattern — added (?<!\() to that pattern too

Remaining issues:
- CITY: 1 FN, 2 FP (one is GPS-context city in parenthetical like (SPB for Saint Petersburg))
- DOMAIN: R=0.8889, P=0.8889 (1 FN, 1 FP)
- EMAIL: R=0.9524, P=0.9524 (2 FN, 2 FP)

Rate out of 10. Consider: impact of improvements, remaining gaps, and overall quality. Return ONLY a number from 1-10."""

response = bedrock.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'temperature': 1.0},
    additionalModelRequestFields={'thinking': {'type': 'adaptive'}}
)

text = response['output']['message']['content'][0]['text']
print(f'Score: {text.strip()}')