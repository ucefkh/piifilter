"""Get Opus 4.8 score for CITY precision/recall fix."""
import json, re, boto3

client = boto3.client("bedrock-runtime", region_name="us-east-1")

eval_prompt = """You are evaluating PIIFilter, a PII detection library. One change was just made:

**CITY detection fix**: Overhauled CITY regex patterns to fix span overlap issues and improve both precision and recall:

1. Country-in-match fix: CITY patterns used to include the following country name in their match. Changed to positive lookahead so the match is just the city name.
2. New standalone patterns: Added patterns for cities followed by comma+postcode.
3. Country-name exclusion: Added negative lookaheads to prevent country names from being matched as cities.
4. Dedup fix: When a wider regex match contains a narrower one for the same entity type, the narrower match is replaced by the wider one.
5. FP fixes: Added Latin and Backticks to exclusion lists.

Impact:
- CITY: Recall 0.9333 -> 1.0000, Precision 0.6667 -> 0.8421
- COUNTRY: Precision 0.8889 -> 0.9000, Recall 1.0
- PERSON: Precision 0.8571 -> 0.9474
- Overall regex: Precision 0.8640 -> 0.8955, Recall 0.9292

Tests: 450/450 passed.

Rate this improvement out of 10. Consider: impact on precision and recall, correctness of the country-in-match fix, generalizability. Provide brief justification then SCORE: X/10."""

response = client.converse(
    modelId="us.anthropic.claude-opus-4-8",
    messages=[{"role": "user", "content": [{"text": eval_prompt}]}],
    additionalModelRequestFields={"thinking": {"type": "adaptive"}},
    inferenceConfig={"temperature": 1.0, "maxTokens": 2048}
)

full_text = ""
for block in response["output"]["message"]["content"]:
    if "text" in block:
        full_text += block["text"]

print(full_text)

score_match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)\s*/?\s*10", full_text)
if score_match:
    score = float(score_match.group(1))
    with open("/tmp/piifilter_last_score.txt", "w") as f:
        f.write(str(score))
    print("\nScore saved:", score)
else:
    score_match2 = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", full_text)
    if score_match2:
        score = float(score_match2.group(1))
        with open("/tmp/piifilter_last_score.txt", "w") as f:
            f.write(str(score))
        print("Score saved (alt):", score)