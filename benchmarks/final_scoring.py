#!/usr/bin/env python3
"""
Final Comprehensive Scoring for PIIFilter
Sends ALL current benchmark numbers to Claude Opus 4.8 for holistic evaluation.

Uses AWS Bedrock profile-based IAM auth (claude-bedrock profile).
"""
import json, re, boto3, os

# Explicitly strip expired bearer token so we fall back to profile IAM keys
for k in ['AWS_BEARER_TOKEN_BEDROCK', 'AWS_CONFIG_FILE', 'AWS_SHARED_CREDENTIALS_FILE']:
    os.environ.pop(k, None)

session = boto3.Session(profile_name='claude-bedrock', region_name='us-east-1')
client = session.client('bedrock-runtime')

# ── 1. RECALL (held-out 20%) ──
recall_pipeline = {
    "overall": "Precision=0.8482  Recall=0.9000  F1=0.8733  TP=486  FP=87  FN=54",
    "strong_entities": {
        "EMAIL":       "Recall=0.9908, Prec=0.9863",
        "PHONE":       "Recall=0.9730, Prec=0.9474",
        "URL":         "Recall=1.0000, Prec=0.9697",
        "IP_ADDRESS":  "Recall=0.9545, Prec=0.8660",
        "PERSON":      "Recall=0.9804, Prec=0.8197",
        "COMPANY":     "Recall=0.9524, Prec=0.8696",
    },
    "weak_entities": {
        "ADDRESS":     "Recall=0.8750, Prec=0.9655",
        "API_KEY":     "Recall=0.7500, Prec=1.0000",
        "CITY":        "Recall=0.7143, Prec=0.7143",
        "COUNTRY":     "Recall=0.8750, Prec=0.7368",
        "CREDIT_CARD": "Recall=0.8125, Prec=0.8254",
        "DOMAIN":      "Recall=0.9286, Prec=0.8125",
        "SOCIAL_SECURITY": "Recall=0.8312, Prec=0.9143",
    },
    "perfect_entities": [
        "BANK_ACCOUNT", "CUSTOMER_NAME", "DATABASE_URL", "DATE",
        "EMPLOYEE_NAME", "FILE_PATH", "GPS", "JWT", "PASSPORT",
        "PROJECT_NAME", "SSH_KEY",
    ],
}
# Masked/obfuscated PII excluded from real-only metrics — already anonymized.

# ── 2. ADVERSARIAL V3 ──
adv_v3 = {
    "total": 201,
    "full_pipeline_rate": 43.8,
    "raw_regex_rate": 28.4,
    "deobfuscation_improvement": "+15.4%",
    "by_category": {
        "Hexadecimal encoding":   {"rate": 100.0, "improvement": "+75.0"},
        "Binary encoding":        {"rate": 100.0, "improvement": "+75.0"},
        "Reversed words":         {"rate": 100.0, "improvement": "+62.5"},
        "Pig-latin style":        {"rate": 100.0, "improvement": "+50.0"},
        "CREDIT_CARD":            {"rate": 64.3,  "improvement": "+64.3"},
        "PASSPORT":               {"rate": 64.3,  "improvement": "+57.1"},
        "BANK_ACCOUNT":           {"rate": 83.3,  "improvement": "-16.7"},
        "GPS":                    {"rate": 100.0, "improvement": "+50.0"},
        "L33tspeak":              {"rate": 85.7,  "improvement": "0"},
        "Emoji substitution":     {"rate": 50.0,  "improvement": "0"},
        "CamelCase split":        {"rate": 100.0, "improvement": "0"},
        "Case-shifted":           {"rate": 40.0,  "improvement": "0"},
        "Double encoding":        {"rate": 20.0,  "improvement": "0"},
        "Unicode fractions":      {"rate": 0.0,   "improvement": "0"},
        "Morse code":             {"rate": 0.0,   "improvement": "0"},
        "Syllabic split":         {"rate": 0.0,   "improvement": "0"},
        "XML escaping":           {"rate": 0.0,   "improvement": "0"},
        "ZWJ interleaving":       {"rate": 0.0,   "improvement": "0"},
        "Punctuation-stuffed":    {"rate": 0.0,   "improvement": "0"},
        "Circular-shifted":       {"rate": 0.0,   "improvement": "0"},
        "CUSTOMER_NAME":          {"rate": 12.5,  "improvement": "0"},
        "IP_ADDRESS":             {"rate": 16.7,  "improvement": "0"},
        "DATE":                   {"rate": 0.0,   "improvement": "0"},
        "EMAIL":                  {"rate": 0.0,   "improvement": "0"},
        "EMPLOYEE_NAME":          {"rate": 0.0,   "improvement": "0"},
    },
}

# ── 3. PERFORMANCE ──
perf = {
    "1KB":  {"p50": "3.10ms", "throughput": "273.3 docs/s", "ms_per_KB": "3.66"},
    "10KB": {"p50": "31.94ms", "throughput": "30.6 docs/s", "ms_per_KB": "3.27"},
    "100KB": {"p50": "363.48ms", "throughput": "2.7 docs/s", "ms_per_KB": "3.71"},
    "target": "<50ms/KB",
    "actual_avg": "3.55ms/KB",
    "status": "PASS (13x under target)",
    "deobfuscator_pct_time": "~20%",
    "bottleneck": "unwrap_at_dot (16.9%)",
}

# ── 4. TESTS ──
tests = {
    "passed": 458,
    "skipped": 25,
    "integration_skipped": "6+11+8=25 (provider real/streaming/unfilter roundtrip — need real API keys)",
    "runtime": "3.18s",
}

# ── 5. CI (last 10 commits) ──
ci_commits = [
    "Fix CREDIT_CARD IBAN FPs: substring-match bug in context-window fallback",
    "fix: prevent l33tspeak decoder from corrupting digit-heavy tokens (passport, IBAN)",
    "fix: eliminate SOCIAL_SECURITY false positives, precision 0.8235->0.9333",
    "8 deobfuscator transforms: hex-escape, binary, l33t, morse, xml-esc, punct-stuff, pig-latin, fractions",
    "fix: tighten SOCIAL_SECURITY patterns to eliminate FPs",
    "Masked CC/SSN patterns + IP 0.942 fix + SSN 0.875, CC 0.813 improvements",
    "fix(addr): extend ADDRESS pattern to capture full address include city/state/zip",
    "Fix PERSON recall: stop deobfuscator from collapsing Dr.->Dr., fix COMPANY from-X FPs",
    "Fix DOMAIN and COMPANY FPs: add email-local-part guard to DOMAIN",
    "Fix PHONE CJK truncation and reduce PHONE FPs",
]

# ── 6. GAPS & OPEN ISSUES ──
gaps = """
GAPS:
1. CITY recall=0.7143, ADDRESS recall=0.8750 — geography still weak
2. CREDIT_CARD recall=0.8125, precision=0.8254 — both below target
3. SOCIAL_SECURITY recall=0.8312 — below 95% target
4. API_KEY recall=0.7500 — needs improvement
5. Adversarial: punctuation-stuffed (0%), morse (0%), unicode-fractions (0%),
   syllabic-split (0%), xml-esc (0%), ZWJ interleaving (0%) — 6 transforms at 0%
6. Adversarial: double-encoding only 20%, URL morse 0%, DATE/EMAIL/EMPLOYEE_NAME adversarial at 0%
7. Pipeline precision=0.8482 — still generating 87 FPs in 473 held-out examples
8. No adversarial coverage for: social security, phone, iban, api_key, jwt, database_url, file_path
"""

# Build the comprehensive prompt
prompt = f"""You are evaluating PIIFilter, a local-first PII detection system that runs fully offline with no external API calls. This is the FINAL comprehensive evaluation. Use ALL the data below — no hand-waving, no rounding up.

## 1. HELD-OUT RECALL (20% held-out, 473 test examples, 540 entities)

PIPELINE OVERALL: Precision=0.8482  Recall=0.9000  F1=0.8733  TP=486  FP=87  FN=54

Strong entities (all >0.95 recall):
- EMAIL: Recall=0.9908, Precision=0.9863 (216/218 detected, near-perfect)
- PHONE: Recall=0.9730, Precision=0.9474 (108/111)
- URL: Recall=1.0000, Precision=0.9697 (64/64)
- IP_ADDRESS: Recall=0.9545, Precision=0.8660 (84/88)
- PERSON: Recall=0.9804, Precision=0.8197 (50/51) — high recall but 11 FPs
- COMPANY: Recall=0.9524, Precision=0.8696 (40/42)

Perfect recall entities (11 types, all 1.000):
BANK_ACCOUNT, CUSTOMER_NAME, DATABASE_URL, DATE, EMPLOYEE_NAME, FILE_PATH,
GPS, JWT, PASSPORT, PROJECT_NAME, SSH_KEY

Weak entities:
- CREDIT_CARD: Recall=0.8125, Precision=0.8254 (52/64, 11 FPs, 12 FNs)
- SOCIAL_SECURITY: Recall=0.8312, Precision=0.9143 (64/77, 6 FPs, 13 FNs)
- CITY: Recall=0.7143, Precision=0.7143 (10/14, 4 FPs, 4 FNs)
- ADDRESS: Recall=0.8750, Precision=0.9655 (28/32)
- API_KEY: Recall=0.7500, Precision=1.0000 (12/16, 0 FPs)
- COUNTRY: Recall=0.8750, Precision=0.7368 (14/16, 5 FPs)
- DOMAIN: Recall=0.9286, Precision=0.8125 (26/28, 6 FPs)

Note: Masked/obfuscated PII (X-encoded, hash-like, hex, base64, spoken-out) are excluded from real-only metrics — already anonymized, not PII leaks.

## 2. ADVERSARIAL V3 (201 challenging obfuscated examples)

OVERALL: Full pipeline detects 43.8%, raw regex 28.4%, deobfuscation improvement +15.4%

Strong adversarial categories:
- Hexadecimal encoding: 100% (+75% vs regex)
- Binary encoding: 100% (+75% vs regex)
- Reversed words: 100% (+62.5% vs regex)
- Pig-latin style: 100% (+50% vs regex)
- CamelCase split: 100%
- GPS: 100% (+50%)
- L33tspeak: 85.7%
- BANK_ACCOUNT: 83.3%
- CREDIT_CARD: 64.3% (+64.3%)
- PASSPORT: 64.3% (+57.1%)

Weak adversarial categories:
- Emoji substitution: 50% (all misses are DOMAIN with emoji)
- Case-shifted: 40%
- Double encoding: 20%
- IP_ADDRESS: 16.7%
- CUSTOMER_NAME: 12.5%
- ZERO PERCENT (8 categories): Punctuation-stuffed, Morse code, Unicode fractions,
  Syllabic split, XML escaping, ZWJ interleaving, Circular-shifted, DATE, EMAIL, EMPLOYEE_NAME

Adversarial coverage gaps (no test data for these entity types):
social_security, phone, iban, api_key, jwt, database_url, file_path, project_name

## 3. PERFORMANCE

| Doc Size | p50(ms) | Throughput | ms/KB |
|----------|---------|------------|-------|
| 1KB      | 3.10ms  | 273.3/s    | 3.66  |
| 10KB     | 31.94ms | 30.6/s     | 3.27  |
| 100KB    | 363.48ms| 2.7/s      | 3.71  |

Target: <50ms/KB → Actual: 3.55ms/KB avg → PASS (13x under target)
Deobfuscator: ~20% of total time. Bottleneck: unwrap_at_dot (16.9% of deobf time)

## 4. UNIT TESTS

458 passed, 25 skipped in 3.18s
Skipped: integration tests requiring real API keys (provider, streaming, unfilter roundtrip)

## 5. RECENT FIXES (last 10 commits)

- CREDIT_CARD IBAN FPs fixed (substring match → word-boundary match)
- l33tspeak decoder guard for digit-heavy tokens
- SOCIAL_SECURITY FP elimination (precision 0.8235→0.9333)
- 8 new deobfuscator transforms added
- ADDRESS pattern extended for city/state/zip
- PERSON Dr.->Dr. collapse fix, COMPANY from-X FP fix
- DOMAIN/COMPANY FP reduction with email-local-part guard
- PHONE CJK truncation fix

## 6. KNOWN GAPS

1. CITY recall=0.7143, ADDRESS recall=0.8750 — geography still weak
2. CREDIT_CARD recall=0.8125, precision=0.8254 — both significant
3. SOCIAL_SECURITY recall=0.8312 (FNs=13) — still losing real SSNs
4. API_KEY recall=0.7500 — needs more pattern coverage
5. Pipeline precision=0.8482 — 87 FPs across 473 examples is too many
6. 8 adversarial categories at 0% detection
7. 8+ PII types have no adversarial test coverage
8. Double encoding adversarial detection only 20%

## FINAL TASK

Based on ALL of the above data (not prior scores, not optimistic projections — these are the real current numbers as of July 19, 2026), please provide:

1. **OVERALL SCORE /10** — a single number representing the system's overall maturity
2. **PER-CATEGORY BREAKDOWN** — score each dimension separately:
   - Held-out recall (precision + recall balance)
   - Adversarial robustness
   - Performance / latency
   - Test coverage / code quality
   - Pattern coverage (number of entity types handled)
3. **SPECIFIC GAP TO 9.5** — what exactly needs to happen to reach 9.5/10
4. **PRIORITY-ORDERED NEXT STEPS** — ordered by impact, with specific targets

Be honest and critical. Use the real numbers. End your response with a line exactly like:
FINAL SCORE: X.X/10
(where X.X is your overall score, one decimal place)
"""

response = client.converse(
    modelId='us.anthropic.claude-opus-4-8',
    messages=[{'role': 'user', 'content': [{'text': prompt}]}],
    inferenceConfig={'temperature': 1.0, 'maxTokens': 8192},
    additionalModelRequestFields={"thinking": {"type": "adaptive"}}
)

all_text = ""
for item in response['output']['message']['content']:
    if 'text' in item:
        all_text += item['text']

all_text = all_text.strip()
print("=" * 72)
print("  CLAUDE OPUS 4.8 — FINAL PIIFilter EVALUATION")
print("=" * 72)
print()
print(all_text)
print()

# Parse score
score_match = re.search(r'FINAL SCORE:\s*(\d+(?:\.\d+)?)\s*/\s*10', all_text)
if score_match:
    score = float(score_match.group(1))
    with open('/tmp/piifilter_final_score.txt', 'w') as f:
        f.write(str(score))
    print(f"─" * 40)
    print(f"  FINAL SCORE: {score}/10")
    print(f"  Saved to /tmp/piifilter_final_score.txt")
else:
    print("─" * 40)
    print("  [WARN] Could not parse FINAL SCORE from response")
    # Try alternate patterns
    alt_match = re.search(r'(?:Score|score|SCORE)[:\s]+(\d+(?:\.\d+)?)\s*/?\s*10', all_text)
    if alt_match:
        score = float(alt_match.group(1))
        print(f"  Found alternate: {score}/10")