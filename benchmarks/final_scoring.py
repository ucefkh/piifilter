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

# ── 1. RECALL (held-out 20%) — PIPELINE-ARBITRATION ──
# Run date: 2026-07-20. Dataset: pii_dataset_v2.json (2365 examples, 473 held-out).
recall_pipeline = {
    "overall": "Precision=0.9077  Recall=0.8757  F1=0.8914  TP=472  FP=48  FN=67",
    "strong_entities": {
        "EMAIL":       "Recall=0.9817, Prec=1.0000",
        "PHONE":       "Recall=0.9825, Prec=1.0000",
        "IP_ADDRESS":  "Recall=0.9783, Prec=0.8036",
        "PERSON":      "Recall=1.0000, Prec=0.7027",
        "BANK_ACCOUNT":"Recall=1.0000, Prec=1.0000",
        "DOMAIN":      "Recall=1.0000, Prec=0.5357",
        "GPS":         "Recall=1.0000, Prec=0.8000",
    },
    "weak_entities": {
        "ADDRESS":     "Recall=0.8947, Prec=0.9444",
        "API_KEY":     "Recall=0.6000, Prec=1.0000",
        "CITY":        "Recall=0.3333, Prec=0.4286",
        "COUNTRY":     "Recall=0.7778, Prec=0.6364",
        "CREDIT_CARD": "Recall=0.6842 (real=0.8667*), Prec=1.0000",
        "COMPANY":     "Recall=0.6364, Prec=1.0000",
        "SOCIAL_SECURITY": "Recall=0.7111 (real=0.8947*), Prec=0.9697",
        "URL":         "Recall=0.6562, Prec=0.9130",
    },
    "perfect_entities": [
        "BANK_ACCOUNT", "CUSTOMER_NAME", "DATABASE_URL", "DATE",
        "FILE_PATH", "GPS", "PASSPORT", "PROJECT_NAME",
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
    "passed": 392,
    "skipped": 25,
    "integration_skipped": "25 (integration tests needing real API keys — provider real/streaming/unfilter roundtrip)",
    "runtime": "3.25s",
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
1. CITY recall=0.3333 — geography extremely weak (3/9 detected)
2. COMPANY recall=0.6364 — lost 8 of 22 companies
3. URL recall=0.6562 — 11 FNs from 32
4. API_KEY recall=0.6000 — 4 of 10 missed
5. CREDIT_CARD recall=0.6842 (real=0.8667*) — obfuscated CCs still missed
6. SOCIAL_SECURITY recall=0.7111 (real=0.8947*) — obfuscated SSNs missed
7. Pipeline precision=0.9077 — 48 FPs in 473 examples (PERSON 11, DOMAIN 13 dominant)
8. PERSON precision=0.7027 — 11 FPs from new communication-verb patterns
9. JWT recall=0.9286 — still losing some tokens
10. Adversarial: 8 transforms at 0% (morse, punctuation-stuffed, unicode fractions, syllabic split, xml escaping, ZWJ interleaving, circular-shifted)
11. No adversarial coverage for: social_security, phone, iban, api_key, jwt, database_url, file_path, project_name
"""

# Build the comprehensive prompt
prompt = f"""You are evaluating PIIFilter, a local-first PII detection system that runs fully offline with no external API calls. This is the FINAL comprehensive evaluation. Use ALL the data below — no hand-waving, no rounding up.

## 1. HELD-OUT RECALL (20% held-out, 473 test examples, ~539 entities)

PIPELINE OVERALL: Precision=0.9077  Recall=0.8757  F1=0.8914  TP=472  FP=48  FN=67

Strong entities (recall >0.95 or precision =1.0):
- EMAIL: Recall=0.9817, Precision=1.0000 (107/109, 0 FPs) — perfect precision
- PHONE: Recall=0.9825, Precision=1.0000 (56/57, 0 FPs) — perfect precision
- IP_ADDRESS: Recall=0.9783, Precision=0.8036 (45/46, 11 FPs)
- PERSON: Recall=1.0000, Precision=0.7027 (26/26, 11 FPs) — perfect recall now
- BANK_ACCOUNT: Recall=1.0000, Precision=1.0000 (perfect)
- DOMAIN: Recall=1.0000, Precision=0.5357 (15/15, 13 FPs)
- GPS: Recall=1.0000, Precision=0.8000
- DATE: Recall=1.0000, Precision=1.0000
- DATABASE_URL: Recall=1.0000, Precision=1.0000
- FILE_PATH: Recall=1.0000, Precision=1.0000
- PASSPORT: Recall=1.0000, Precision=1.0000
- CUSTOMER_NAME: Recall=1.0000, Precision=1.0000
- PROJECT_NAME: Recall=1.0000, Precision=1.0000

Weak entities (recall <0.90):
- CREDIT_CARD: Recall=0.6842 (real masked=0.8667*), Prec=1.0000 (26/38, 0 FPs, 12 FNs — all FNs are obfuscated)
- SOCIAL_SECURITY: Recall=0.7111 (real masked=0.8947*), Prec=0.9697 (32/45, 1 FP, 13 FNs — all FNs obfuscated)
- URL: Recall=0.6562, Precision=0.9130 (21/32, 2 FPs, 11 FNs)
- CITY: Recall=0.3333, Precision=0.4286 (3/9, 4 FPs, 6 FNs) — very weak
- COMPANY: Recall=0.6364, Precision=1.0000 (14/22, 0 FPs, 8 FNs)
- API_KEY: Recall=0.6000, Precision=1.0000 (6/10, 0 FPs, 4 FNs)
- ADDRESS: Recall=0.8947, Precision=0.9444 (17/19)
- COUNTRY: Recall=0.7778, Precision=0.6364 (7/9, 4 FPs, 2 FNs)
- JWT: Recall=0.9286, Precision=0.9286 (13/14)

Note: Masked/obfuscated PII (X-encoded, hash-like, hex, base64, spoken-out) are excluded from real-only metrics — already anonymized, not PII leaks.
(*) Asterisk marks recall columns where obfuscated entries are excluded.

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

392 passed, 25 skipped in 3.25s
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

1. CITY recall=0.3333 — extremely weak, geography needs full rebuild
2. COMPANY recall=0.6364 — corporate entity detection needs major improvement
3. URL recall=0.6562 — URL pattern coverage is too narrow
4. API_KEY recall=0.6000 — API keys being missed
5. CREDIT_CARD recall=0.6842 (but real masked=0.8667*) — obfuscated CCs
6. SOCIAL_SECURITY recall=0.7111 (but real masked=0.8947*) — obfuscated SSNs
7. Pipeline precision=0.9077 — 48 FPs (PERSON 11 from new verb patterns, DOMAIN 13)
8. PERSON precision=0.7027 — 11 FPs needs tightening
9. 8 adversarial transforms at 0% detection
10. 8+ PII types have no adversarial test coverage
11. Company, City, URL, API_KEY are still below 80% recall

## FINAL TASK

Based on ALL of the above data (not prior scores, not optimistic projections — these are the real current numbers as of July 20, 2026), please provide:

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